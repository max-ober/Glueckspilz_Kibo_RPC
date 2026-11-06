#!/usr/bin/env python3
import rospy
import subprocess
from std_msgs.msg import String
from ib2_msgs.msg import Navigation
from krpc_ib2_msgs.srv import MissionStart, MissionFinished, CheckPoints
from pprint import pprint
import json


class Maestro:
    def __init__(self):
            rospy.init_node('maestro')
            rospy.loginfo("Maestro started")

            #rospy.Subscriber("/sensor_fusion/navigation", Navigation, self.print_pos)
            self.raw_checkpoints = rospy.ServiceProxy('/mission/get_checkpoints', CheckPoints)
            self.read_checkpoints()

            rospy.spin()
    
    def print_pos(self, data):
         print(data)

    # from user_template.py
    def __get_checkpoint_id(self, checkpoint):
            for key in ('checkpoint_id', 'checkpointid', 'id'):
                if key in checkpoint:
                    return int(checkpoint[key])
            return None

    def read_checkpoints(self):
        rospy.wait_for_service('/mission/get_checkpoints')
        response = self.raw_checkpoints()
        if not response.success:
             rospy.loginfo("Could not read checkpoints!")
             return
        try:
            payload = json.loads(response.message)
            checkpoints = payload.get('checkpoints', payload.get('Checkpoints', []))
            checkpoints = [cp for cp in checkpoints if isinstance(cp, dict) and self.__get_checkpoint_id(cp) is not None]
            if not checkpoints:
                rospy.logwarn('No checkpoints found in payload')
                return
            
            rospy.loginfo(f"Successfully loaded {len(checkpoints)} checkpoints")
            for cp in checkpoints:
             #rospy.loginfo(f"=> Checkpoint {cp.checkpoint_id}: position: {cp.position}, attitude: {cp.attitude.quaternion}, marker: {cp.marker_pose}, ")
             #rospy.loginfo(json.dumps(cp, indent=2))
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
        except Exception as e:
                    rospy.logwarn('Failed to parse checkpoints payload: %s', e)
        return checkpoints


def summon_maestro():
    subprocess.Popen(["rosrun", "krpc_user" ,"maestro.py"])

if __name__ == '__main__':
    m = Maestro()
