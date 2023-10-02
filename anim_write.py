"""To be run in Maya. Nothing special happening in this script, just boilerplate

Saves animation from Maya scene to a .anim.xml file

(anim.xml = intermediate filetype that will be converted to .dwanim.xml by dwanim_convert.py)

Summary
0. Assumes Maya scene with humanoid animating
1. For each frame in the working time range
    2. Read each joint's rotation (and translation in the case of the root/hips)
    3. Write all those rotations (in good ol' eulers) into a new frame of the new xml tree
4. Save xml tree to .anim.xml file in the anims directory
"""

import maya.cmds as cmd

import xml.etree.ElementTree as xml # our anims need to be saved in xml format

from os.path import join

# Globals
EXPORT_FOLDER = r"R:\Code\DeepWalkerAnims\anims"
DEFAULT_EXPORT_BASENAME = "standard_walk"
HUMANOID_NAMESPACE = "humanoid_hik"
DEFAULT_BASE_NODE = HUMANOID_NAMESPACE + ":geo:base"
FPS = 30 #Default 30. On import/run, calls get_maya_fps

HUMANOID_JOINT_NAMES = [
    "root",
    "chest",
    "neck",
    "right_shoulder",
    "right_elbow",
    "right_wrist",
    "left_shoulder",
    "left_elbow",
    "left_wrist",
    "right_hip",
    "right_knee",
    "right_ankle",
    "left_hip",
    "left_knee",
    "left_ankle"
] # Index in this list = DWJointIndex

# Copied from DeepWalker\common.py
# Index in this list = DWJointIndex
DW_JOINT_NAMES = ('Root', 'Chest', 'Neck', 'RShoulder', 'RElbow', 'RWrist', 'LShoulder', 'LElbow', 'LWrist', 'RHip', 'RKnee', 'RAnkle', 'LHip', 'LKnee', 'LAnkle')

# Classes
# TODO This should just access Deepwalker\common.py's version of the same class
# But Maya has trouble importing that, so for now I'm copying
class MayaJointState:
    """Kinematic data about a joint (or any object, really), in maya space.
    Current rotation, rotational velocity, position, and positional velocity.

    For context, here are the data structures where this class is used:
    - An anim pose is constituted as a dictionary of joint names to these.
    - A deepwalker pose is constituted as a tuple, with indices matching each DWJointIndex, where each element is a small tuple containing the motor control value and one of these.
    """
    def __init__(self, lrot=[0.0, 0.0, 0.0], lrotvel=[0.0, 0.0, 0.0], wrot=[0.0, 0.0, 0.0], wrotvel=[0.0, 0.0, 0.0], wpos=[0.0, 0.0, 0.0], wposvel=[0.0, 0.0, 0.0]):
        """
        Args:
            wrot (3 float list, optional): Parent-space rotation. Defaults to None.
            wrotvel (3 float list, optional): Parent-space rotational velocity. Defaults to None.
            wpos (3 float list, optional): World-space position. Defaults to None.
            wposvel (3 float list, optional): World-space positional velocity. Defaults to None.
        """
        self.lrot = lrot
        self.lrotvel = lrotvel
        self.wrot = wrot
        self.wrotvel = wrotvel
        self.wpos = wpos
        self.wposvel = wposvel
    
    def flattened(self):
        """Get this anim joint state's values as a single tuple of 12 floats. Order: lrot, lrotvel, wrot, wrotvel, wpos, wposvel

        Returns:
            tuple: Tuple containing this instance's values
        """
        return tuple(self.lrot + self.lrotvel + self.wrot + self.wrotvel + self.wpos + self.wposvel)

    # To Strings
    def __str__(self):
        return "<MayaJointState: lrot={:<4} lrotvel={:<4} wrot={:<4} wrotvel={:<4} wpos={:<4} wposvel={:<4}>".format(self.lrot, self.lrotvel, self.wrot, self.wrotvel, self.wpos, self.wposvel)

    def __format__(self): return self.__str__()

    def __repr__(self): return self.__str__()




def export_anim( filename=DEFAULT_EXPORT_BASENAME, base=DEFAULT_BASE_NODE ):

    xml_root = xml.Element("anim")
    xml_tree = xml.ElementTree(xml_root)

    
    # Get time info
    m_start_frame = int( cmd.playbackOptions( q = True, minTime = True ) )
    m_end_frame = int( cmd.playbackOptions( q = True, maxTime = True ) )
    m_frame_step = 1
    print("start: {}, end: {}".format(m_start_frame, m_end_frame))

    # 1. For each frame in the working time range
    for frame_no, m_frame in enumerate( range( m_start_frame, m_end_frame, m_frame_step ) ):
        # frame_no: Int, from zero, the index of the frame in the xml
        # m_frame: Maya-format frame number, can be used as time for maya cmds

        # 2. Read each joint's rotation (and translation in the case of the root/hips)
        # 3. Write all those rotations (in good ol' eulers) into a new frame of the new xml tree
        _add_frame_to_xml(xml_root, frame_no, m_frame)

    # TODO Make indents
    # My Maya's version of python (2.something) doesn't have an indent function in its xml library
    # For now I can format in VSCode (Alt+Shift+F)
    #xml.indent(xml_tree) # Only exists in 3.9

    # 4. Save xml tree to .anim.xml file in the anims directory
    filepath = join( EXPORT_FOLDER, filename ) + ".anim.xml"
    xml_tree.write(filepath)

    print("Exported animation to {}".format(filepath))


# Based on dwanim_convert._add_timestep_to_xml
def _add_frame_to_xml(anim_root, frame_no, m_frame):
    frame_tree = xml.SubElement(anim_root , "frame")

    no_elem = xml.SubElement(frame_tree, "no")
    no_elem.text = str(frame_no)

    pose_elem = xml.SubElement(frame_tree, "pose")

    # Get each joint name, should be in index order already
    for index, joint_name in enumerate(HUMANOID_JOINT_NAMES):
        # Find joint by name
        m_joint = HUMANOID_NAMESPACE + ":skel:" + joint_name
        if not cmd.objExists(m_joint):
            print("{} does not exist".format(m_joint))
            continue
        print("[{}]: {}".format(index, m_joint))

        state = get_joint_state( m_joint, m_frame )

        _add_joint_to_xml( pose_elem, joint_name, state )


# Based on dwanim_convert._add_dwjoint_xml_element
def _add_joint_to_xml(parent_tree, name, state):
    """Adds xml elements from data about a maya joint

    Args:
        parent_tree (Element/Tree): _description_
        name (str): _description_
        state (MayaJointState): _description_
    """
    joint_elem = xml.SubElement(parent_tree, "joint")

    index_elem = xml.SubElement(joint_elem, "name")
    index_elem.text = name

    _add_3f_xml_element(joint_elem, "lrot", "y", state.lrot[0], "p", state.lrot[1], "r", state.lrot[2])

    _add_3f_xml_element(joint_elem, "lrotvel", "y", state.lrotvel[0], "p", state.lrotvel[1], "r", state.lrotvel[2])

    _add_3f_xml_element(joint_elem, "wrot", "y", state.wrot[0], "p", state.wrot[1], "r", state.wrot[2])

    _add_3f_xml_element(joint_elem, "wrotvel", "y", state.wrotvel[0], "p", state.wrotvel[1], "r", state.wrotvel[2])

    _add_3f_xml_element(joint_elem, "wpos", "x", state.wpos[0], "y", state.wpos[1], "z", state.wpos[2])

    _add_3f_xml_element(joint_elem, "wposvel", "x", state.wposvel[0], "y", state.wposvel[1], "z", state.wposvel[2])


# TODO This should just access dwanim_convert.py's version of the same function
# But Maya has trouble importing that, so for now I'm copying
def _add_3f_xml_element(parent_tree, name, float1_name, float1, float2_name, float2, float3_name, float3):
    # Add element
    elem = xml.SubElement(parent_tree, name)

    # Add subelement and set its value
    float1_elem = xml.SubElement(elem, float1_name)
    float1_elem.text = str(float1)

    # Add subelement and set its value
    float2_elem = xml.SubElement(elem, float2_name)
    float2_elem.text = str(float2)

    # Add subelement and set its value
    float3_elem = xml.SubElement(elem, float3_name)
    float3_elem.text = str(float3)

    return elem, float1_elem, float2_elem, float3_elem


# TODO put this in some common file
########################################################################################
# THE IMPORTANT FUNCTION
def get_joint_state(m_joint, m_frame, get_vel = True):
    """
    Gets a joint's translation, rotation, etc. and puts it in a MayaJointState class

    Args:
        joint (str): Joint name
        prev_joint_state (MayaJointState, optional): Same joint's state on the previous frame. Defaults to None (= no velocity).
    """
    kwargs = {}

    # Go to time
    cmd.currentTime( m_frame )

    # Get rotation and translation
    lrot = cmd.xform( m_joint, q = True, rotation = True, objectSpace = True )
    wrot = cmd.xform( m_joint, q = True, rotation = True, worldSpace = True )
    wpos = cmd.xform( m_joint, q = True, translation = True, worldSpace = True )

    # Add to arguments
    kwargs["lrot"] = lrot
    kwargs["wrot"] = wrot
    kwargs["wpos"] = wpos

    # Only make velocities if there's a previous to compare to
    if get_vel:
        # Get previous frame's position and rotation
        prev_state = get_joint_state( m_joint, m_frame - 1, get_vel = False ) # Recursive

        delta_time = 1.0 / FPS

        # Calculate rotational velocity
        prev_lrot = prev_state.lrot
        lrotvel = cmd.angleBetween( vector1 = prev_lrot, vector2 = lrot, euler = True )
        lrotvel = [ delta_time * x for x in lrotvel ]

        # Calculate rotational velocity (world)
        prev_wrot = prev_state.wrot
        wrotvel = cmd.angleBetween( vector1 = prev_wrot, vector2 = wrot, euler = True )
        wrotvel = [ delta_time * x for x in wrotvel ]

        # Calculate positional velocity
        prev_wpos = prev_state.wpos
        wposvel = [ ( wpos[i] - prev_wpos[i] ) * delta_time for i in range(len(wpos)) ]

        # Add to arguments
        kwargs["lrotvel"] = lrotvel
        kwargs["wrotvel"] = wrotvel
        kwargs["wposvel"] = wposvel

    return MayaJointState(**kwargs)
########################################################################################


def get_maya_fps():
    fps_str = cmd.currentUnit( q = True, time = True )
    if not fps_str.endswith("fps"):
        fps_codes = {
            "game": 15,
            "film": 24,
            "pal": 25,
            "ntsc": 30,
            "show": 48,
            "palf": 50,
            "ntscf": 60
        }
        fps = fps_codes.get(fps_str, -1)
        if fps == -1:
            print("Error: Unknown Maya FPS '{}'".format(fps_str))
            return -1
        return fps

    fps_str = fps_str.partition("fps")[0]
    return float(fps_str)



FPS = get_maya_fps()
if __name__ == "__main__":
    export_anim()