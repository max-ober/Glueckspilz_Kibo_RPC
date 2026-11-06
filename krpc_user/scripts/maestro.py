#!/usr/bin/env python3
import rospy
import subprocess
import actionlib
from copy import deepcopy
from platform_msgs.msg import UserLogic
from std_msgs.msg import String
from ib2_msgs.msg import Navigation
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from platform_msgs.srv import StopProcessingUserNode, StopProcessingUserNodeResponse
from ib2_msgs.msg import CtlCommandAction, CtlCommandGoal, CtlCommandResult, CtlStatusType
from pathfinder import solve_tsp
from pprint import pprint
import json
from typing import List, Tuple, Dict


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

        # === Actions ===
        self.__command = actionlib.SimpleActionClient('/ctl/command', CtlCommandAction)
        
        
        self.__started = False
        self.__action_active = False
        rospy.set_param('/ib2_user/ready', True) # DO NOT REMOVE THIS LINE

    def spin(self):
        rospy.spin()

    def run(self, msg):
        if not self.__notify_mission_start():
            return
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

        #TODO: ADD MOVEMENT LOGIC HERE

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