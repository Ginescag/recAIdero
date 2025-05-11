#codigo hecho por Gines Caballero Guijarro

'''
 rosrun slam_pkg recAIdero.py --map src/slam_pkg/Maps/finalWorld.yaml --query "ves a por mi kfc"

 RECUERDA CARGAR EL MAPA EN SLAM CON:

 roslaunch turtlebot3_navigation turtlebot3_navigation.launch map_file:=/workspace/catkin_ws/src/slam_pkg/Maps/finalWorld.yaml

'''
#!/usr/bin/env python3
"""
recaidero_ros_node.py
 - Interpreta lenguaje natural para elegir destino.
 - Tras llegar, espera y vuelve a casa automáticamente.
 - Can be controlled via command-line arguments.
"""

import argparse
import re
import sys
import yaml
import time
import rospy
import actionlib
import tf 
import tf.transformations as tft
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
from actionlib_msgs.msg import GoalStatus
from geometry_msgs.msg import Quaternion, Point, Pose

DESTINATIONS = {
# ...existing code...
    "kfc":        (-7.0,   7.0,   0.0),
    "mcdonalds":  (-7.0,  -7.0,   0.0),
    "house":      (0.0, 0.0,   3.14159)   # “casa” → punto de retorno
}
HOME_KEY = "house"          # cuál es tu “casa”
WAIT_SECONDS = 10           # tiempo de recogida
ROBOT_BASE_FRAME = "base_footprint" 
MAP_FRAME = "map"


KEYWORDS = {

    r"\bkfc\b|\bkentucky\b|\bpollo\b|\brojo\b"      : "kfc",
    r"\bmcd(ona)?lds\b|\bmac\b|\bm[ck]donald'?s\b"  : "mcdonalds",
    r"\bhouse\b|\bcasa\b|\bhogar\b|\bbeige\b"       : "house"
}

def quat_from_yaw(yaw):

    q = tft.quaternion_from_euler(0, 0, yaw)
    return Quaternion(*q)

def parse_nlp(text):

    text = text.lower()
    for pattern, dest in KEYWORDS.items():
        if re.search(pattern, text):
            return dest
    nums = re.findall(r"[-+]?[0-9]*\\.?[0-9]+", text)
    if len(nums) >= 2:
        try:
            return (float(nums[0]), float(nums[1]), 0.0) 
        except ValueError:
            return None 
    return None

def load_yaml(path):

    try:
        with open(path) as f: data = yaml.safe_load(f)
        rospy.loginfo("Mapa cargado (res=%.3f)", data.get('resolution', 0))
    except Exception as e:
        rospy.logwarn("No pude leer %s (%s)", path, e)

def move_base_client():

    cli = actionlib.SimpleActionClient('move_base', MoveBaseAction)
    rospy.loginfo("Esperando a move_base…")
    cli.wait_for_server()
    return cli

def get_current_robot_pose(tf_listener):
    """Gets the current pose of the robot in the map frame."""
    try:

        tf_listener.waitForTransform(MAP_FRAME, ROBOT_BASE_FRAME, rospy.Time(0), rospy.Duration(1.0))
        (trans, rot) = tf_listener.lookupTransform(MAP_FRAME, ROBOT_BASE_FRAME, rospy.Time(0))
        euler = tft.euler_from_quaternion(rot)
        yaw = euler[2]
        return (trans[0], trans[1], yaw)
    except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException, tf.Exception) as e:
        rospy.logwarn(f"No se pudo obtener la pose actual del robot: {e}")
        return None

def send_goal(cli, target, label="objetivo"):

    x, y, yaw = target
    goal = MoveBaseGoal()
    goal.target_pose.header.stamp    = rospy.Time.now()
    goal.target_pose.header.frame_id = MAP_FRAME
    goal.target_pose.pose.position.x = x
    goal.target_pose.pose.position.y = y
    goal.target_pose.pose.orientation = quat_from_yaw(yaw)

    rospy.loginfo("Enviando %s (%.2f, %.2f, %.1f°)…", label, x, y, yaw*57.3)
    cli.send_goal(goal)
    cli.wait_for_result()
    state = cli.get_state()
    return state == GoalStatus.SUCCEEDED


def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("--map",  required=True, help="Path to the map YAML file")
    ap.add_argument("--query", help="Natural language query for destination")
    ap.add_argument("--dest", choices=DESTINATIONS.keys(), help="Direct destination key")
    ap.add_argument("--go_home_now", action="store_true", help="Skip query and go directly to home.")
    args, _ = ap.parse_known_args() 

    try:
        rospy.init_node("recaidero_ros_node", anonymous=True)
    except rospy.exceptions.ROSInitException as e:
        print(f"ERROR: Failed to initialize ROS node. Is roscore running? {e}", file=sys.stderr)
        sys.exit(1)

    tf_listener = tf.TransformListener() 

    load_yaml(args.map)
    client = move_base_client()

    if args.go_home_now:
        rospy.loginfo("Comando de cancelación/retorno directo recibido: Volviendo a casa.")
        home_target = DESTINATIONS[HOME_KEY]
        if send_goal(client, home_target, "casa (retorno directo)"):
            rospy.loginfo("🏠 Llegamos a casa. ¡Trabajo terminado!")
        else:
            rospy.logwarn("No pudimos volver a casa tras el comando de retorno directo.")
            current_pose = get_current_robot_pose(tf_listener)
            if current_pose:
                rospy.logwarn(f"Última posición conocida del robot: X={current_pose[0]:.2f}, Y={current_pose[1]:.2f}, Yaw={current_pose[2]:.2f} rad")
        sys.exit(0)


    target = None
    dest_key = "destino desconocido"

    if args.dest:
        dest_key = args.dest
        target   = DESTINATIONS[dest_key]
    elif args.query:
        query = args.query
        rospy.loginfo(f"Procesando consulta: {query}")
        res = parse_nlp(query)
        if res is None:
            rospy.logerr("No entiendo el destino de la consulta.")
            sys.exit(1)
        if isinstance(res, str):
            dest_key = res
            target   = DESTINATIONS[dest_key]
        else:
            dest_key = f"coordenadas ({res[0]:.2f}, {res[1]:.2f})"
            target   = res
    else:
        rospy.logerr("Se requiere --query o --dest o --go_home_now.")
        sys.exit(1)

    # -------- Ir al destino --------

    if target:
        if send_goal(client, target, dest_key):
            rospy.loginfo("✅ Llegamos a %s", dest_key)
        else:
            rospy.logwarn("No pudimos alcanzar %s", dest_key)
            current_pose = get_current_robot_pose(tf_listener)
            if current_pose:
                rospy.logwarn(f"Última posición conocida del robot: X={current_pose[0]:.2f}, Y={current_pose[1]:.2f}, Yaw={current_pose[2]:.2f} rad")
            sys.exit(1)
    else:
        rospy.logerr("No se determinó un objetivo válido.")
        sys.exit(1)

    # -------- Esperar y anunciar recogida --------
    if dest_key != HOME_KEY: 
        rospy.loginfo("⌛ Esperando %d s para recoger pedido…", WAIT_SECONDS)
        time.sleep(WAIT_SECONDS) 
        rospy.loginfo("✅ Pedido recogido: regreso a casa…")

        # -------- Volver a casa --------
        home_target = DESTINATIONS[HOME_KEY]
        if send_goal(client, home_target, "casa (retorno automático)"):
            rospy.loginfo("🏠 Llegamos a casa. ¡Trabajo terminado!")
        else:
            rospy.logwarn("No pudimos volver a casa automáticamente.")
            current_pose = get_current_robot_pose(tf_listener)
            if current_pose:
                rospy.logwarn(f"Última posición conocida del robot: X={current_pose[0]:.2f}, Y={current_pose[1]:.2f}, Yaw={current_pose[2]:.2f} rad")
    else:
        rospy.loginfo("Ya estamos en casa o el destino era casa. ¡Trabajo terminado!")


if __name__ == "__main__":

    try:
        main()
    except rospy.ROSInterruptException:
        rospy.loginfo("Proceso interrumpido (ROS).")
    except KeyboardInterrupt:
        rospy.loginfo("Proceso interrumpido (Ctrl+C).")
    except Exception as e:
        print(f"ERROR IN RECAIDERO ROS NODE: {e}", file=sys.stderr)

        sys.exit(1)

