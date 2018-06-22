#!/usr/bin/env python
import rospy
from sensor_msgs.msg import Image
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
import math
import matplotlib.pyplot as plt
import time

import signal
import sys

camera_matrix = np.array(
        [[608.91474407072610, 0, 318.06264860718505],
         [0, 568.01764400596119, 242.18421070925399],
         [0, 0, 1]], dtype="double"
    )

valid_last_orientation = False

def signal_handler(signal, frame):
    sys.exit(0)


def find_threshold_bimodal(array):
    array = np.array(array,dtype="double")
    array_sum = np.sum(array)
    var = []
    for n in range(array.size):
        partarray_sum = np.sum(array[:n])
        if partarray_sum == 0:
            s1 = 0
            var1 = 0
        else:
            s1 = np.sum(array[:n]) / array_sum
            mean1 = np.sum(array[:n] * range(n)) / partarray_sum
            var1 = np.sum(np.square(range(n) - mean1) * array[:n] / array_sum / s1)

        partarray_sum = np.sum(array[n:])
        if partarray_sum == 0:
            s2 = 0
            var2 = 0
        else:
            s2 = np.sum(array[n:]) / array_sum
            mean2 = np.sum(array[n:] * range(n, array.size)) / partarray_sum
            var2 = np.sum(np.square(range(n, array.size) - mean2) * array[n:] / array_sum / s2)
        var.append(int(s1 * var1 + s2 * var2))
    idx = (var.index(min(var)) + len(var) - 1 - var[::-1].index(min(var)))/2

    if idx >= 90:
        angle_thres = idx - 90
    else:
        angle_thres = idx

    return angle_thres


def isect_lines(line1, line2):
    for x1, y1, x2, y2 in line1:
        for x3, y3, x4, y4 in line2:
            try:
                s = float((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / float((x4 - x3) * (y2 - y1) - (x2 - x1) * (y4 - y3))

                x = x3 + s * (x4 - x3)
                y = y3 + s * (y4 - y3)

            except ZeroDivisionError:
                return -1,-1, -1
                print "ZeroDivisionError in isect_lines"
    return x, y


class bebop_image:
    def __init__(self):
        self.image_pub = rospy.Publisher("/auto/bebop_image_CV",Image)

        self.bridge = CvBridge()
        self.image_sub = rospy.Subscriber("/bebop/image_raw",Image,self.callback)

    def callback(self,data):
        try:
            rgb = self.bridge.imgmsg_to_cv2(data, "bgr8")
        except CvBridgeError as e:
            print(e)

        # convert to HSV
        # hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)


def rectify_image(im):
    # Camera internals
    size = im.shape
    image_width = size[0]  # px
    sensor_width = 3.6  # mm
    focal_distance = 4.0  # mm
    focal_length = image_width * focal_distance / sensor_width

    # center = (size[1] / 2, size[0] / 2)
    # camera_matrix = np.array(
    #    [[focal_length, 0, center[0]],
    #     [0, focal_length, center[1]],
    #     [0, 0, 1]], dtype="double"
    # )

    #camera_matrix = np.array(
    #    [[608.91474407072610, 0, 318.06264860718505],
    #     [0, 568.01764400596119, 242.18421070925399],
    #     [0, 0, 1]], dtype="double"
    #)

    # print "Camera Matrix :\n {0}".format(camera_matrix)
    dist_coeffs = np.array(
        [[-4.37108312526e-01, 1.8776063621e-01, -4.6697911662e-03, 2.2242731991e-03 - 9.4929117169e-03]],
        dtype="double")

    # acquire its size
    h = size[0]
    w = size[1]

    # Generate new camera matrix from parameters
    newcameramatrix, roi = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w, h), 0)

    # Generate look-up tables for remapping the camera image
    mapx, mapy = cv2.initUndistortRectifyMap(camera_matrix, dist_coeffs, None, newcameramatrix, (w, h), 5)

    # Remap the original image to a new image
    im_rect = cv2.remap(im, mapx, mapy, cv2.INTER_LINEAR)

    return im_rect


def mask_image(im):
    # convert to HSV
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)

    # Threshold the HSV image to get only orange colors
    # lower_color = np.array([40, 0, 0])       # blue
    # upper_color = np.array([180, 150, 150])  # blue
    # lower_color = np.array([6, 230, 110])  # orange 2D
    # upper_color = np.array([14, 255, 200])  # orange 2D
    lower_color = np.array([6, 150, 10])  # orange 3D
    upper_color = np.array([14, 255, 240])  # orange 3D

    mask = cv2.inRange(hsv, lower_color, upper_color)

    # Bitwise-AND mask and original image
    #res = cv2.bitwise_and(rgb, rgb, mask=mask)
    #cv2.imshow('frame', res)

    return mask


if __name__ == '__main__':
    cap = cv2.VideoCapture(2)
    i=0
    while True:
        # time.sleep(5)

        # Capture and rectify frames
        ret, rgb_in = cap.read()
        rgb = rectify_image(rgb_in)

        # Continue without lens distortion
        dist_coeffs = np.zeros((4, 1))

        # HSV conversion and frame detection
        mask = mask_image(rgb)

        #if cv2.waitKey(1) & 0xFF == ord('q'):
        #    break
        #continue

        # probabilistic hough transform
        minLineLength = 50
        maxLineGap = 30

        lines = cv2.HoughLinesP(mask, 1, np.pi / 180, 50, minLineLength, maxLineGap)
        if lines is None:
            print "no lines"

        else:  # lines have been found
            # calculate angles of all lines and create a border of the gate location
            angles = []

            borders = [1000,0,1000,0]
            for counter, line in enumerate(lines):
                for x1, y1, x2, y2 in line:
                    angles.append(math.atan2(y2 - y1, x2 - x1)*180/np.pi)  # between -90 and 90
                    # cv2.line(rgb, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    borders[0] = min(borders[0], x1, x2)
                    borders[1] = max(borders[1], x1, x2)
                    borders[2] = min(borders[2], y1, y2)
                    borders[3] = max(borders[3], y1, y2)

            # border = np.array([[borders[0],borders[2]],[borders[0],borders[3]],[borders[1],borders[3]],[borders[1],borders[2]]], np.int32)
            # border = border.reshape((-1, 1, 2))
            # cv2.polylines(rgb, [border], True, (100,100,100), 5)

            # intersect every line with every other line
            corners_long = []
            for i1, l1 in enumerate(lines):
                for i2, l2 in enumerate(lines[:i1]):
                    angles_diff = math.fabs(angles[i1]-angles[i2])
                    if 10 < angles_diff < 170:  # only intersect if they are not clos to parallel
                        x, y = isect_lines(l1, l2)
                        # only use those intersections that lie within bounding box of gate
                        if (    borders[0] - 0.2 * (borders[1] - borders[0]) < x < borders[1] + 0.2 * (borders[1] - borders[0]) and
                                borders[2] - 0.2 * (borders[3] - borders[2]) < y < borders[3] + 0.2 * (borders[3] - borders[2])):
                            corners_long.append([x, y])
                            #cv2.circle(rgb, (int(x), int(y)), 1, (255, 255, 255), -1)

            if len(corners_long) == 0:  # no corners have been found
                print "no corners"

            else:
                # corners were found, find average and center

                #plt.clf()
                #plt.plot(corners_long)
                #plt.scatter(*zip(*corners_long))

                # while there are still corners to sort, use the first in the list and look for all corners in vicinity
                corners = []
                while len(corners_long)>0:
                    xm, ym = corners_long.pop(0)
                    votes = 1
                    i = 0
                    while i < len(corners_long):  # go through whole list once
                        x1, y1 = corners_long[i]
                        dist = math.sqrt((xm-x1)*(xm-x1)+(ym-y1)*(ym-y1))  # calculate distance of each point
                        if dist < 60:  # if distance is small enough, recalculate point center and add one vote, then delete from list
                            xm = (xm * votes + corners_long[i][0]) / (votes + 1)
                            ym = (ym * votes + corners_long[i][1]) / (votes + 1)
                            votes = votes + 1
                            del corners_long[i]
                        else:  # otherwise continue with next item
                            i = i+1
                    corners.append([xm, ym, votes])


                for x, y, v in corners:
                    cv2.circle(rgb, (int(x), int(y)), 10, (0, 0, 255), -1)


                # delete the corners with the least number of votes
                while len(corners) > 4:
                    votes = zip(*corners)[2]
                    del corners[votes.index(min(votes))]

                for x, y, v in corners:
                    cv2.circle(rgb, (int(x), int(y)), 10, (255, 0, 0), -1)


                square_side = 0.1015
                if len(corners) < 3:
                    print "Found only two points or less"
                    valid_last_orientation = False
                elif len(corners) == 3 and not valid_last_orientation:
                    print "3 points without a guess"

                else:
                    if len(corners) == 3:
                        corner_points = np.array([[corners[0][0], corners[0][1]], [corners[1][0], corners[1][1]],
                                                  [corners[2][0], corners[2][1]]], dtype="double")
                        # 3D model points.
                        model_points = np.array([
                            (+square_side / 2, +square_side / 2, 0.0),
                            (+square_side / 2, -square_side / 2, 0.0),
                            (-square_side / 2, +square_side / 2, 0.0)])

                        (success, rvec, tvec) = cv2.solvePnP(model_points, corner_points,
                                                                                      camera_matrix,
                                                                                      dist_coeffs,rvec, tvec,True,
                                                                                      flags=cv2.SOLVEPNP_ITERATIVE)
                        valid_last_orientation = True
                        print success

                    elif len(corners) == 4:
                        corner_points = np.array([[corners[0][0], corners[0][1]], [corners[1][0], corners[1][1]],
                                                  [corners[2][0], corners[2][1]], [corners[3][0], corners[3][1]]],
                                                 dtype="double")
                        # 3D model points.
                        model_points = np.array([
                            (+square_side / 2, +square_side / 2, 0.0),
                            (+square_side / 2, -square_side / 2, 0.0),
                            (-square_side / 2, +square_side / 2, 0.0),
                            (-square_side / 2, -square_side / 2, 0.0)])
                        (success, rvec, tvec) = cv2.solvePnP(model_points, corner_points, camera_matrix,
                                                                                      dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)
                        valid_last_orientation = True

                    #print "Rotation Vector:\n {0}".format(rvec)
                    rmat, _ = cv2.Rodrigues(rvec)
                    #print "Rotation Matrix:\n {0}".format(rmat)
                    if rmat[0][0] < 0:
                        rmat = np.array([[-rmat[0][0], rmat[0][1], -rmat[0][2]],
                                [-rmat[1][0], rmat[1][1], -rmat[1][2]],
                                [-rmat[2][0], rmat[2][1], -rmat[2][2]]])

                    rvec2, _ = cv2.Rodrigues(rmat)

                    print rvec[0], rvec[1], rvec[2], rvec2[0], rvec2[1], rvec2[2]
                    #print "nl"

                    # print "Translation Vector:\n {0}".format(tvec)

                    # draw a line sticking out of the plane
                    (center_point_2D_base, jacobian_1) = cv2.projectPoints(np.array([(.0, .0, 0)]), rvec, tvec, camera_matrix, dist_coeffs)
                    (center_point_2D_back, jacobian_2) = cv2.projectPoints(np.array([(.0, .0, square_side)]), rvec, tvec, camera_matrix, dist_coeffs)
                    (center_point_2D_frnt, jacobian_2) = cv2.projectPoints(np.array([(.0, .0, -square_side)]), rvec, tvec, camera_matrix, dist_coeffs)

                    p1 = (int(center_point_2D_back[0][0][0]), int(center_point_2D_back[0][0][1]))
                    p2 = (int(center_point_2D_frnt[0][0][0]), int(center_point_2D_frnt[0][0][1]))
                    p3 = (int(center_point_2D_base[0][0][0]), int(center_point_2D_base[0][0][1]))

                    if max(p1) < 10000 and max(p2) < 10000 and min(p1) > 0 and min(p2) > 0:
                        cv2.line(rgb, p1, p3, (0, 255, 255), 10)
                        cv2.line(rgb, p2, p3, (0, 255, 255), 10)
                    if max(p3) < 10000 and min(p3) > 0:
                        cv2.circle(rgb, p3, 10, (0, 0, 0), -1)


        # Display the resulting frame
        cv2.imshow('frame', rgb)
        # cv2.imshow('frame', hsv)
        #plt.xlim((-1000,1500))
        #plt.ylim((-700,1200))
        #plt.pause(0.01)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # When everything done, release the capture
    cap.release()
    cv2.destroyAllWindows()


#    signal.signal(signal.SIGINT, signal_handler)
#    rospy.init_node('bebop_image', anonymous=True)
#    bebop_image()

#    cameraMatrix = [396.17782, 0.0, 322.453185, 0.0, 399.798333, 174.243174, 0.0, 0.0, 1.0]
#    vector < Point3f > objectPoints
#    objectPoints.push_back(Point3f(0.44, 0.30, 0.46));
    # cv2.solvePnP(objectPoints, imagePoints, cameraMatrix, distCoeffs[, rvec[, tvec[, useExtrinsicGuess[, flags]]]]) ----> retval, rvec, tvec

#    rospy.spin()
