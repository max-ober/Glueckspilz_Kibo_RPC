#!/usr/bin/env python3
"""Mover node: serves `move_to_target` and drives /ctl/command (MOVE_TO_ABSOLUTE_TARGET).

Goal:     geometry_msgs/Pose target   (frame iss_body)
Feedback: distance to target [m], from /sensor_fusion/navigation
Result:   success, final distance [m], last known pose
"""
import math
import threading

import actionlib
import rospy
from geometry_msgs.msg import Pose, PoseStamped
from ib2_msgs.msg import (CtlCommandAction, CtlCommandGoal, CtlCommandResult,
                          CtlStatus, CtlStatusType, Navigation)
from krpc_user.msg import (move_to_targetAction, move_to_targetFeedback,
                           move_to_targetResult)

NAV_TOPIC = '/sensor_fusion/navigation'
CTL_ACTION = '/ctl/command'
SERVER_NAME = 'move_to_target'
STATUS_TOPIC = '/ctl/status'


class Mover:
    def __init__(self):
        rospy.init_node('mover')
        self.__timeout = rospy.get_param('~move_timeout', 90.0)  # s per move
        self.__server_wait = rospy.get_param('~server_wait', 30.0)  # s
        self.__rate = rospy.Rate(10)

        self.__pose_lock = threading.Lock()
        self.__pose = None  # latest Pose from navigation

        rospy.Subscriber(NAV_TOPIC, Navigation, self.__cb_nav, queue_size=1)
        
        self.__ctl_state = None
        rospy.Subscriber(STATUS_TOPIC, CtlStatus, self.__cb_status, queue_size=1)
        self.__ctl = actionlib.SimpleActionClient(CTL_ACTION, CtlCommandAction)
        rospy.loginfo('mover: waiting for %s', CTL_ACTION)
        if not self.__ctl.wait_for_server(rospy.Duration(self.__server_wait)):
            rospy.logerr('mover: %s not available, continuing anyway', CTL_ACTION)

        self.__server = actionlib.SimpleActionServer(
            SERVER_NAME, move_to_targetAction, execute_cb=self.__execute, auto_start=False)
        self.__server.start()
        rospy.on_shutdown(self.__on_shutdown)
        rospy.loginfo('mover: ready')

    # ---------------------------------------------------------------- helpers
    def __cb_nav(self, msg):
        with self.__pose_lock:
            self.__pose = msg.pose.pose

    def __get_pose(self):
        with self.__pose_lock:
            return self.__pose

    def __cb_status(self, msg):
        self.__ctl_state = msg.type.type   

    def __wait_for_hold(self, timeout=2.0):
        end = rospy.Time.now() + rospy.Duration(timeout)
        while not rospy.is_shutdown() and rospy.Time.now() < end:
            if self.__ctl_state in (CtlStatusType.KEEP_POSE,
                                    CtlStatusType.STOP_MOVING):
                return True
            rospy.sleep(0.05)
        return False

    @staticmethod
    def __distance(a, b):
        return math.sqrt((a.position.x - b.position.x) ** 2 +
                         (a.position.y - b.position.y) ** 2 +
                         (a.position.z - b.position.z) ** 2)

    def __current_distance(self, target):
        pose = self.__get_pose()
        return -1.0 if pose is None else self.__distance(pose, target)

    def __finish(self, success, target, preempted=False):
        result = move_to_targetResult()
        result.success = success
        result.distance = self.__current_distance(target)
        pose = self.__get_pose()
        result.position = pose if pose is not None else Pose()
        if preempted:
            self.__server.set_preempted(result)
        elif success:
            self.__server.set_succeeded(result)
        else:
            self.__server.set_aborted(result)

    def __cancel_ctl(self):
        self.__ctl.cancel_goal()
        if not self.__ctl.wait_for_result(rospy.Duration(5.0)):
            rospy.logwarn('mover: cancel did not complete in time')

    # ---------------------------------------------------------------- action
    def __execute(self, goal):
        target = goal.target
        stamped = PoseStamped()
        stamped.header.frame_id = 'iss_body'
        stamped.header.stamp = rospy.Time.now()
        stamped.pose = target

        ctl_goal = CtlCommandGoal(
            target=stamped,
            type=CtlStatusType(type=CtlStatusType.MOVE_TO_ABSOLUTE_TARGET))

        rospy.loginfo('mover: moving to [%.3f %.3f %.3f]',
                      target.position.x, target.position.y, target.position.z)
        self.__ctl.send_goal(ctl_goal)
        start = rospy.Time.now()

        while not rospy.is_shutdown():
            if self.__server.is_preempt_requested():
                rospy.logwarn('mover: preempted, cancelling move')
                self.__cancel_ctl()
                self.__finish(False, target, preempted=True)
                return

            if self.__ctl.wait_for_result(rospy.Duration(0.1)):
                res = self.__ctl.get_result()
                ok = res is not None and res.type == CtlCommandResult.TERMINATE_SUCCESS
                code = None if res is None else res.type
                rospy.loginfo('mover: ctl result code=%s success=%s state=%s',
                            code, ok, self.__ctl_state)
                held = self.__wait_for_hold()
                rospy.loginfo('mover: after wait, held=%s state=%s', held, self.__ctl_state)
                if ok and not self.__wait_for_hold():
                    rospy.logwarn('mover: no KEEP_POSE/STOP_MOVING after success (state=%s)',
                                self.__ctl_state)
                self.__finish(ok, target)
                return

            if (rospy.Time.now() - start).to_sec() > self.__timeout:
                rospy.logwarn('mover: move timed out after %.1fs', self.__timeout)
                self.__cancel_ctl()
                self.__finish(False, target)
                return

            fb = move_to_targetFeedback()
            fb.distance = self.__current_distance(target)
            self.__server.publish_feedback(fb)
            self.__rate.sleep()

        # ROS shutting down
        self.__cancel_ctl()
        self.__finish(False, target)

    def __on_shutdown(self):
        try:
            self.__ctl.cancel_all_goals()
        except Exception:
            pass

    def spin(self):
        rospy.spin()


if __name__ == '__main__':
    Mover().spin()
