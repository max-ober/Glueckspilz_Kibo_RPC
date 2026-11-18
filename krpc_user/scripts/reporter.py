import rospy
from krpc_ib2_msgs.msg import CheckpointPassedGoal



def pass_checkpoint(checkpoint_id, checkpoint_client) -> bool:
    rospy.loginfo('notify checkpoint_id=%d passed', checkpoint_id)
    checkpoint_client.wait_for_server()
    goal = CheckpointPassedGoal()
    goal.checkpoint_id = checkpoint_id
    checkpoint_client.send_goal(goal)
    while not rospy.is_shutdown():
        if checkpoint_client.wait_for_result(rospy.Duration(0.2)):
            result = checkpoint_client.get_result()
            rospy.loginfo('checkpoint_passed result: %s', result)
            return result.success
    if rospy.is_shutdown():
        checkpoint_client.cancel_goal()
        rospy.logwarn('checkpoint_passed action cancelled by node shutdown')
    return False

def send_final_report(mission_finished_service):
    rospy.wait_for_service('/event/mission_finished')
    res = mission_finished_service()
    rospy.loginfo('mission_finished result: success=%s message=%s', res.success, res.message)
    return res.success