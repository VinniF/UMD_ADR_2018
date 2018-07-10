#!/usr/bin/env python

#  --- Changelog ---
# Goal:     Input by bebop camera and state_machine to detect that gate has been passed. Output advances state_machine
# Status:   06/19: Not existing
#           06/25: Empty file

import rospy
import roslaunch
import time
from subprocess import check_output
from geometry_msgs.msg import Twist, Pose
import math
import signal
import sys
import time
from bebop_msgs.msg import Ardrone3PilotingStateFlyingStateChanged
from std_msgs.msg import Bool, Int32


def signal_handler(signal, frame):
    sys.exit(0)


def received_update(data, args):
    global drone
    global path_visual
    global path_blind
    global state_machine

    if args == "position":
        drone = data
    elif args == "path_visual":
        path_visual = data
    elif args == "path_blind":
        path_blind = data
    elif args == "state_machine":
        state_machine = data.data


def main():
    # Enable killing the script with Ctrl+C.
    signal.signal(signal.SIGINT, signal_handler)

    rospy.init_node('gate_crossing_detection', anonymous=True)

    global drone
    global path_visual
    global path_blind
    global state_machine
    drone = None
    path_visual = None
    path_blind = None
    state_machine = -1
    rospy.Subscriber("/auto/odometry_merged",   Pose, received_update, "position")
    rospy.Subscriber("/auto/path_blind",        Pose, received_update, "path_blind")
    rospy.Subscriber("/auto/path_visual",       Pose, received_update, "path_visual")
    rospy.Subscriber("/auto/state_machine",    Int32, received_update, "state_machine")

    state_publisher = rospy.Publisher("/auto/state_machine", Int32, queue_size=1, latch=True)

    rate = rospy.Rate(20)

    while True:
        rate.sleep()

        # set applicable path
        if path_visual is None:
            if path_blind is not None:
                path = path_blind
            else:
                # rospy.loginfo("no path")
                continue
        else:
            path = path_visual

        if drone is None:
            # rospy.loginfo("no position")
            continue

        diff_global = [path.position.x - drone.position.x,
                       path.position.y - drone.position.y,
                       path.position.z - drone.position.z]

        distance = math.sqrt(
            diff_global[0] * diff_global[0] + diff_global[1] * diff_global[1] + diff_global[2] * diff_global[2])

        if state_machine == 4:
            if distance < 0.5:
                rospy.loginfo("too close to WP")
                state_publisher.publish(state_machine + 1)

        if state_machine == 5:
            if distance < 0.05:
                rospy.loginfo("Target reached")
                state_publisher.publish(state_machine + 1)

        if state_machine == 6:
            if distance < 0.05:
                rospy.loginfo("landing reached")
                state_publisher.publish(state_machine + 1)



if __name__ == '__main__':
    main()
