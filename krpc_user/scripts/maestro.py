#!/usr/bin/env python3
import rospy
import subprocess
import actionlib
from copy import deepcopy
from geometry_msgs.msg import Pose
from platform_msgs.msg import UserLogic
from std_msgs.msg import String
from ib2_msgs.msg import Navigation
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType
from krpc_user.msg import move_to_targetAction, move_to_targetGoal
from krpc_ib2_msgs.msg import CheckpointPassedAction
import json
from typing import List, Tuple, Dict

from pathfinder import solve_tsp
from reporter import pass_checkpoint, send_final_report




class Maestro:
    def __init__(self):
        rospy.init_node('maestro')
        rospy.loginfo("Maestro started")

        # === Subscribers  ===
        self.__subscriber_start = rospy.Subscriber('/ib2_user/start', UserLogic, self.__callback_start)  # DO NOT REMOVE THIS LINE

        # === Services ===
        self.__stop_processing_server = rospy.Service('/ib2_user/stop', StopProcessingUserNode, self.__stop_processing) # DO NOT REMOVE THIS LINE
        self.__mission_start = rospy.ServiceProxy('/event/mission_start', MissionStart)
        self.raw_checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)
        self.__mission_finished_service = rospy.ServiceProxy('/event/mission_finished', MissionFinished)

        # === Actions ===
        self.__command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        self.__checkpoint_client = actionlib.SimpleActionClient('/event/checkpoint_passed', CheckpointPassedAction)
        
        
        self.__started = False
        self.__action_active = False
        rospy.set_param('/ib2_user/ready', True) # DO NOT REMOVE THIS LINE

    def spin(self):
        rospy.spin()

    def __hold_position(self, seconds: float) -> bool:
        """Stay put for `seconds`. Returns False if ROS is shutting down."""
        rospy.loginfo("Holding position for %.2fs", seconds)
        end = rospy.Time.now() + rospy.Duration.from_sec(seconds)
        while rospy.Time.now() < end:
            if rospy.is_shutdown():
                return False
            rospy.sleep(0.05)
        return True

    def run(self, msg):
        if not self.__notify_mission_start():
            return

        # Rulebook: all 3 conditions must hold for 1 s. Add a small margin
        # for settling and for the judge's timer start.
        hold_time = rospy.get_param('~hold_time', 1.2)
        retry_hold = rospy.get_param('~retry_hold', 0.5)
        max_pass_retries = rospy.get_param('~max_pass_retries', 2)

        self.cp_list, self.cp_dict, self.goal_id  = self.read_checkpoints()

        #find best path - start point taken from programming manual
        start_point = {
                "checkpoint_id": 0,
                "position": [0.2, 0, 0],
                "attitude": {
                    "quaternion": [0, 0, 0, 1]
                }
        }
        goal_cp = self.cp_dict[self.goal_id]
        cp_without_goal = deepcopy(self.cp_list)
        cp_without_goal.remove(goal_cp)
        path_length, path = solve_tsp(cp_without_goal, start_point, goal_cp)
        rospy.loginfo(path_length)
        rospy.loginfo(path)

        rospy.loginfo("Checkpoint dictionary keys: %s",
              list(self.cp_dict.keys()))

        rospy.loginfo("Calculated path: %s", path)

        rospy.loginfo("Goal ID: %s", self.goal_id)

        # MOVEMENT LOGIC HERE

        mover = actionlib.SimpleActionClient(
            'move_to_target',
            move_to_targetAction
        )

        if not mover.wait_for_server(rospy.Duration(30)):
            rospy.logerr("MoveToTarget Action Server not available")
            return

        # follow calculated path to traverse all checkpoints
        for checkpoint_id in path:

            
            checkpoint = self.cp_dict[checkpoint_id]

            # get pose of checkpoint
            pose = Pose()

            pose.position.x = checkpoint["position"][0]
            pose.position.y = checkpoint["position"][1]
            pose.position.z = checkpoint["position"][2]

            pose.orientation.x = checkpoint["attitude"]["quaternion"][0]
            pose.orientation.y = checkpoint["attitude"]["quaternion"][1]
            pose.orientation.z = checkpoint["attitude"]["quaternion"][2]
            pose.orientation.w = checkpoint["attitude"]["quaternion"][3]

            goal = move_to_targetGoal()
            goal.target = pose

            rospy.loginfo("Moving to checkpoint %s", checkpoint_id)

            mover.send_goal(goal)

            # wait until move is finished
            finished = mover.wait_for_result(rospy.Duration(90))

            if not finished:
                rospy.logerr("Movement timed out at checkpoint %s", checkpoint_id)
                mover.cancel_goal()
                continue

            result = mover.get_result()

            if result is None or not result.success:
                rospy.logerr("Movement failed at checkpoint %s", checkpoint_id)
                continue

            rospy.loginfo(
                "Reached checkpoint %s. Distance: %s",
                checkpoint_id,
                result.distance
            )

            # Hold position for at least 1s
            if not self.__hold_position(hold_time):
                return

            # Report the checkpoint; retry a bounded number of times, each time 
            # holding a little longer
            passed = pass_checkpoint(checkpoint_id, self.__checkpoint_client)
            retries = 0
            while not passed and retries < max_pass_retries:
                retries += 1
                rospy.logwarn("Checkpoint %s not passed, retry %d/%d",
                              checkpoint_id, retries, max_pass_retries)
                if not self.__hold_position(retry_hold):
                    return
                passed = pass_checkpoint(checkpoint_id, self.__checkpoint_client)

            if not passed:
                rospy.logwarn("Failed checkpoint %s", checkpoint_id)
                continue
            rospy.loginfo("Checkpoint %s passed", checkpoint_id)

        rospy.loginfo("All checkpoints completed, sending final report")
        result = send_final_report(self.__mission_finished_service)
        if result: rospy.loginfo(f"Successfully finished the mission!")
        else: rospy.logwarn("Mission did not finish successfully")


    def __callback_start(self, msg):
            if self.__started:
                rospy.logwarn('start callback is already processed')
                return
            self.__started = True
    
            rospy.loginfo('start %s', msg)
            self.run(msg)

    def __get_checkpoint_id(self, checkpoint):
            for key in ('checkpoint_id', 'checkpointid', 'id'):
                if key in checkpoint:
                    return int(checkpoint[key])
            return None

    def read_checkpoints(self) -> Tuple[List, Dict, int]:
        rospy.wait_for_service('/mission/get_checkpoints')
        response = self.raw_checkpoints()
        if not response.success:
            rospy.loginfo("Could not read checkpoints!")
            return ([], {}, -1)
        try:
            payload = json.loads(response.message)
            cp_list = payload.get('checkpoints', payload.get('Checkpoints', []))
            cp_list = [cp for cp in cp_list if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None]
            if not cp_list:
                rospy.logwarn('No checkpoints found in payload')
                return ([], {}, -1)
            
            rospy.loginfo(f"Successfully loaded {len(cp_list)} checkpoints")
            cp_dict = {}
            for cp in cp_list:
                rospy.loginfo(
                    f"--- Checkpoint ID: {cp['checkpoint_id']} ---\n"
                    f"  Position: {cp['position']}\n"
                    f"  Marker Pose Position: {cp['marker_pose']['position']}\n"
                    f"  Marker Pose Quaternion: {cp['marker_pose']['quaternion']}\n"
                    f"  Score Bands: {cp['score_bands']}\n"
                    f"  Attitude Quaternion: {cp['attitude']['quaternion']}\n"
                    f"  Centering Bands: {cp['attitude']['centering_bands']}\n"
                    f"  Roll Bands: {cp['attitude']['roll_bands']}"
                )
                cp_dict[cp['checkpoint_id']] = cp
            goal_id = payload["goalpoint_id"]
        except Exception as e:
                    rospy.logwarn('Failed to parse checkpoints payload: %s', e)
        return (cp_list, cp_dict, goal_id)

    def __stop_processing(self, request):
        try:
            if self.__action_active:
                self.__command.cancel_goal()
            rospy.loginfo('finish processing')
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.SUCCESS)
        except Exception as exc:
            rospy.logerr('stop processing failed: %s', exc)
            return StopProcessingUserNodeResponse(result=StopProcessingUserNodeResponse.ERROR)

    def __notify_mission_start(self):
        rospy.wait_for_service('/event/mission_start')
        res = self.__mission_start()
        rospy.loginfo('mission_start result: success=%s message=%s', res.success, res.message)
        return res.success

    

def summon_maestro():
    subprocess.Popen(["rosrun", "krpc_user" ,"maestro.py"])

if __name__ == '__main__':
    Maestro().spin()