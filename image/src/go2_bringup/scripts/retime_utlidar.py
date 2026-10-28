#!/usr/bin/env python3

import copy

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import PointCloud2
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


class RetimeUtlidar(Node):
    def __init__(self):
        super().__init__('retime_utlidar')

        self.tf_broadcaster = TransformBroadcaster(self)

        self.cloud_pub = self.create_publisher(
            PointCloud2,
            '/utlidar/cloud_deskewed_retimed',
            10
        )
        # cloud_base is already firmware-transformed into base_link, unlike
        # cloud_deskewed (frame_id odom, world-fixed) -- safe to retime with
        # arrival time alone, no TF-lookup-time dependency to get wrong.
        self.cloud_base_pub = self.create_publisher(
            PointCloud2,
            '/utlidar/cloud_base_retimed',
            10
        )
        self.odom_pub = self.create_publisher(
            Odometry,
            '/utlidar/robot_odom_retimed',
            10
        )

        self.cloud_sub = self.create_subscription(
            PointCloud2,
            '/utlidar/cloud_deskewed',
            self.cloud_callback,
            10
        )
        self.cloud_base_sub = self.create_subscription(
            PointCloud2,
            '/utlidar/cloud_base',
            self.cloud_base_callback,
            10
        )
        self.odom_sub = self.create_subscription(
            Odometry,
            '/utlidar/robot_odom',
            self.odom_callback,
            10
        )

        self.get_logger().info('retime_utlidar node started')

    def cloud_callback(self, msg: PointCloud2):
        out = copy.deepcopy(msg)
        out.header.stamp = self.get_clock().now().to_msg()
        self.cloud_pub.publish(out)

    def cloud_base_callback(self, msg: PointCloud2):
        out = copy.deepcopy(msg)
        out.header.stamp = self.get_clock().now().to_msg()
        self.cloud_base_pub.publish(out)

    def odom_callback(self, msg: Odometry):
        out = copy.deepcopy(msg)
        now = self.get_clock().now().to_msg()
        out.header.stamp = now
        self.odom_pub.publish(out)

        tf_msg = TransformStamped()
        tf_msg.header.stamp = now
        tf_msg.header.frame_id = out.header.frame_id      # usually "odom"
        tf_msg.child_frame_id = out.child_frame_id        # usually "base_link"

        tf_msg.transform.translation.x = out.pose.pose.position.x
        tf_msg.transform.translation.y = out.pose.pose.position.y
        tf_msg.transform.translation.z = out.pose.pose.position.z
        tf_msg.transform.rotation = out.pose.pose.orientation

        self.tf_broadcaster.sendTransform(tf_msg)


def main(args=None):
    rclpy.init(args=args)
    node = RetimeUtlidar()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()