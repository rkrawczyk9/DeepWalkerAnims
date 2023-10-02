"""
What This Is
---------------------------------------------------------
URDF = Universal Robot Description Format
Maya = A 3D animation program


This script builds a URDF robot in Maya, minus the physics functionality, so you can retarget animations from 
other characters in Maya to your robot's proportions and axis orientations.

Intended to be run in the Maya Script Editor. (I'm using Maya 2020, but this should work in recent Maya version.)


Instructions
---------------------------------------------------------
0. To be safe, convert any URDF files you're using to be UTF-8 (BOM) encoding, using Notepad++ or something.
1. New Scene
2. Click the bottom-est right button (Script Editor)
3. File > Open Script. Select this script. Select Python if prompted (not MEL)
4. If you want to make something besides the humanoid, change the bottom line of this script to use
        your URDF's filepath rather than DEFAULT_URDF_PATH.
5. Click the double Play button.
6. Hopefully it worked. Hit 6 to see the pretty colors.


Applications
---------------------------------------------------------
The final goal, once this script has
built your robot in Maya, and you have somehow put animation on its skeleton, is to be able to query each joint's
rotation at each timestep (called a 'frame' in animation land,) so you can bring these rotations into a physics
environment (like pybullet) to use as reference poses for machine learning-based character control.

*Maya rotations are Eulers, so you'll probably need to convert them to Quaternions to use them as joint control values
in pybullet for example, because pybullet's spherical joints use Quaternions for control values.


I'll be working on scripts to support the rest of this process soon.


Hierarchy Plan
---------------------------------------------------------
URDFs are made up of joints and links. It's an alternating hierarchy, meaning it goes...

| base link
| | joint
| | | link
| | | | joint
| | | | | link
| | | | | | joint
| | | | | | | link
| | joint
| | | link

But animation land prefers to have the joints in a hierarchy (aka. a "skeleton"), and the links (aka. geo) attached to that.
So the links should never be involved in the hierarchy really; the skeleton drives everything, and the links just follow.
(It's like this because animation characters don't need to do physics, receive forces on geo, etc.)

This script first creates and places the objects in a hierarchy like above, then reorganizes the hierarchy to be like this:

| joint1
| | geo1
| | joint2
| | | geo2
| | | joint3
| | | | geo3
| | joint4
| | | geo4


*Special case:
The concept of a base link in URDFs does not work directly with animation land. (The base link has its own independent
position and rotation.) In animation land, this would be a joint, not a geo. (Ex. for bipeds, the pelvis/Hips joint.)
So in Maya we'll create a joint as the root of the hierarchy, rather than a geo, and attach the base geo to it. This
should be the only object we'll have in Maya that is not represented in the URDF file.



Parsing the URDF
------------------------------------------------------------
For links, we'll need the 'collision' element to become the Maya geo object - 'geometry' decides which
primitive to create, and 'origin' becomes its transform. We have no use for 'inertial' as far as I can tell.

For joints, as you would expect, 'parent' will tell us the joint's parent. And 'child' will tell us which geo
object to attach to this joint.
"""
# Imports

# Maya Commands
import maya.cmds as cmd

# So we can import our packages from our virtual environment
# NOT WORKING (GAVE UP, just used default libraries)
"""
VENV_LIB_PATH = r"R:\Code\DeepWalker\deepwalker_venv\Lib\site-packages"
import sys
if VENV_LIB_PATH not in sys.path:
    sys.path.append( VENV_LIB_PATH )"""

# Import XML-reading lib. URDFs are in XML
import xml.etree.ElementTree as xml

# Angle function
# Initially wanted to use pybullet's, for continuity, but it's hard to import in maya.
#from pybullet import getEulerFromQuaternion
# Actually not sure we need to convert from quats at all in this file.
from math import degrees


# Globals

# *Convert your URDFs to UTF8-BOM encoding beforehand, so python's ElementTree lib can
#       parse them. By default the URDF I got from pybullet_data was in ANSI encoding which
#       is not supported. I opened the URDF file in Notepad++ and did Encoding > Convert to UTF-8-BOM.
DEFAULT_URDF_PATH = r"R:\Code\DeepWalkerAnims\maya_urdf\humanoid_utf8-bom.urdf"

# Conversion factor!
SPACE_RATIO_URDF_TO_MAYA = 10

CAPSULE_MATS = None # Initialized in _init_mats
SPHERE_MATS = None # Initialized in _init_mats
BOX_MATS = None # Initialized in _init_mats
MAT_COUNTER = 0 # To sequentially choose colors as we go through the hierarchy

# Main
def build_urdf(urdf_path):
    """Builds a model replicating a URDF robot, in Maya.
    Assumes a new Maya scene is open.
    Joint rotation channel values should be able be extracted as ctrl values to be used by the URDF.

    See the docstring at the top of this file for more explanation, also the Resources folder.

    Args:
        urdf_path (str): Path to the URDF file to replicate.
    """
    # Variable name convention: "u_" = thing from URDF file, "m_" = thing in Maya

    # Open up URDF
    try:
        u_tree = xml.parse(urdf_path)
    except Exception as e:
        msg = "Couldn't parse XML file. If the path is correct, please convert it to UTF-8 BOM encoding."
        print("\nmaya_build_urdf.py: {}\n\n{}\n\nPath: {}".format(e, msg, urdf_path))
        cmd.error(msg)
        return

    # Read URDF tree
    u_root = u_tree.getroot()
    u_links = u_root.findall("link")
    u_joints = u_root.findall("joint")

    # Set up Maya scene
    print ("Setting up the Maya scene")
    if not cmd.namespace(exists="geo"):
        cmd.namespace(add = "geo")
    if not cmd.namespace(exists="skel"):
        cmd.namespace(add = "skel")

    # Create materials
    _init_mats()

    # Do it!
    # First, create all the geos
    print( "Creating the geo..." )
    m_geos_and_shapes = [ _build_geo(u_l) for u_l in u_links ]
    
    
    # Then, create the alternating hierarchy, by attaching each joint to its parent geo, and attaching the child geo to the joint
    print("Creating the alternating hierarchy..." )
    m_joints = [ _build_joint_into_hierarchy(u_j) for u_j in u_joints ]


    # Finally, clean up the hierarchy by separating out the geos (no longer alternating)
    print("Reorganizing the hierarchy...")
    m_joints = [ _reparent_joint(m_j) for m_j in m_joints ]


    # Assign materials
    # We do this afterwards because when reparenting objects, it unassigns the material somehow
    for m_geo, u_shape in m_geos_and_shapes:
        _assign_mat(m_geo, u_shape)
    

    print("Done!")
    


def _build_geo(u_link):
    """Creates a geometry object resembling a URDF collision geometry.

    Supports spheres, capsules, and boxes. A link without a collision is created as a locator.

    Args:
        u_link (xml.Element): A <link> from a URDF file

    Returns:
        [str, str]: Name of the new object in Maya, and its shape string ("sphere", "capsule", "box", or "locator")
    """
    # Parse and Convert Everything
    m_name = "geo:" + u_link.get("name")
    u_inertial = u_link.find("inertial")
    u_collision = u_link.find("collision")
    if not u_collision:
        print("Creating locator for link '{}' because it has no collision (probably the base)".format(u_link.get("name")))
        u_shape = "locator"
        m_origin = _parse_and_convert_transform( u_inertial.find("origin") )
        m_radius = m_length = m_size = None
    else:
        m_origin = _parse_and_convert_transform( u_collision.find("origin") )
        u_geo = u_collision.find("geometry")[0]
        u_shape = u_geo.tag
        m_radius = _convert_urdf_dist( _parse_float( u_geo.get("radius") ) )
        m_length = _convert_urdf_dist( _parse_float( u_geo.get("length") ) )
        m_size = _convert_urdf_vector( _parse_multi_float( u_geo.get("size") ) )
    
    # Print Found Stuff
    print_rows = [
        ["Link", m_name],
        ["Collision", u_collision],
        ["Origin", m_origin],
        ["Shape", u_shape],
        ["Radius", m_radius],
        ["Length", m_length],
        ["Size", m_size]
    ]
    print("\nBuilding Link Geo\n" + _tabulate(print_rows))

    # Build Shapes (at origin) in Maya
    cmd.select(clear=True) # Deselect so it starts with no parent
    if u_shape == "sphere":
        m_geo = cmd.polySphere(name = m_name, radius = m_radius)[0]
    elif u_shape == "capsule":
        # Create a capsule (cylinder with round caps)
        m_geo = cmd.polyCylinder(   name = m_name,
                                    axis = [0,0,1], # Create sideways (Z) like URDFs expect, rather than default (Y)
                                    radius = m_radius, 
                                    height = m_length, # The endcaps are included in this height, so we don't have to subtract the radius
                                    roundCap = True, 
                                    subdivisionsCaps = 3)[0]
    elif u_shape == "box":
        m_geo = cmd.polyCube(name = m_name, width = m_size[0], height = m_size[1], depth = m_size[2])[0]
    elif u_shape == "locator":
        m_geo = cmd.spaceLocator(name = m_name)
    else:
        print("Can't build geo '{}': unknown type '{}'".format(m_name, u_shape))
        return [None,None]
    
    # Put shape at its future local offset
    # When we parent it to its parent joint, we'll make the command preserve these numbers
    cmd.xform(m_geo, **m_origin)

    # Freeze Transforms. It seems that URDFs expect this
    cmds.makeIdentity(apply=True, t=True, r=True, s=True) # Freeze Transforms

    return [m_geo, u_shape]


def _build_joint_into_hierarchy(u_joint):
    """Create the joint using the URDF data, and parent its designated parent and child links, with correct
    offsets/origins.
    This results in an alternating hierarchy: geo, joint, geo, joint, etc.

    Args:
        u_joint (xml.Element): A <joint> from a URDF file

    Returns:
        str: Name of the new joint in Maya
    """
    # Parse and Convert Everything
    m_name = "skel:" + u_joint.get("name")
    u_parent = u_joint.find("parent").get("link")
    m_parent = "geo:" + u_parent
    if not cmd.objExists(m_parent):
        print("Couldn't find parent geo '{}' for joint '{}'".format(m_parent, m_name))
    m_child = "geo:" + u_joint.find("child").get("link")
    m_origin = _parse_and_convert_transform( u_joint.find("origin") )
    # Could get limit and axis here, for revolute (hinge) joints. But I don't think that's needed for retargeting with HIK

    # Print Found Stuff
    print_rows = [
        ["Joint", m_name],
        ["Parent", m_parent],
        ["Child", m_child],
        ["Origin", m_origin]
    ]
    print("\nBuilding Joint\n" + _tabulate(print_rows))

    # Create Joint
    cmd.select(clear=True) # Deselect so it starts with no parent
    m_joint = cmd.joint(name = m_name) # Create joint

    # Parent Joint to specified parent
    try:
        m_joint = cmd.parent(m_joint, m_parent)[0]
    except:
        #print("Couldn't parent {} to {}".format(m_joint, m_parent))
        pass
    # Offset from parent
    cmd.xform(m_joint, **m_origin)

    # Parent specified child geo to Joint
    cmd.parent(m_child, m_joint, relative=True)

    return m_joint


def _reparent_joint(m_joint):
    """Re-parents the joint from its current geo parent to the joint of the same name, if it exists.
    The geo remains as a child of its joint of the same name. (And now this joint is siblings with that geo)
    
    Un-alternates the part of the hierarchy.

    Args:
        m_joint (str): Maya joint name (namespace necessary)

    Returns:
        str: The joint's name. Currently no use for this return value - eventually could implement full paths, and this would be needed.
    """
    # Get parent
    parents = cmd.listRelatives( m_joint, parent = True )
    if not parents:
        return m_joint
    parent = parents[0]

    # Get joint of same name (different namespace)
    parent_corresponding_joint = _get_joint( parent )
    if cmd.objExists(parent_corresponding_joint) and parent != parent_corresponding_joint:
        # Parent this joint to the joint of the same name
        m_joint = cmd.parent(m_joint, parent_corresponding_joint)[0]
    else:
        print("Skipped reparenting {} from {} to {}".format(m_joint, parent, parent_corresponding_joint))
    return m_joint


def _assign_mat(m_geo, u_shape):
    """Assigns a sequentially chosen material to the geo. Slightly different materials depending on its shape ("capsule", "sphere", "box")

    Args:
        m_geo (str): Maya geo object name
        u_shape (str): Shape name ("capsule", "sphere", or "box")

    Returns:
        bool: True if a material was assigned, False if not. For example, returns False for locators or unidentified shape strings.
    """
    if u_shape == "capsule":
        mats = CAPSULE_MATS
    elif u_shape == "sphere":
        mats = SPHERE_MATS
    elif u_shape == "box":
        mats = BOX_MATS
    else:
        return False
    
    # Sequentally choose colors, so no two geos next to eachother should have the same color
    global MAT_COUNTER
    mat = mats[ MAT_COUNTER % len(mats) ]
    MAT_COUNTER += 1

    # Assign the material
    cmd.select(m_geo)
    cmd.hyperShade(assign = mat)
    #cmd.sets( [m_geo], e=True, forceElement = mat ) # alternate method. mat must be a SG
    return True
    

def _init_mats():
    """Creates materials in the Maya scene to be used later by _assign_mat, if they don't already exist.
    Supposed to resemble the humanoid URDF as seen in pybullet"
    """
    global CAPSULE_MATS
    global SPHERE_MATS
    global BOX_MATS
    if CAPSULE_MATS and SPHERE_MATS and BOX_MATS:
        return

    CAPSULE_MATS = [
        _create_checkerboard_mat(name="cap_r", color1=[1,0,0], color2=[.6,0,0]),
        _create_checkerboard_mat(name="cap_g", color1=[0,1,0], color2=[0,.6,0]),
        _create_checkerboard_mat(name="cap_b", color1=[0,0,1], color2=[0,0,.6]),
        _create_checkerboard_mat(name="cap_y", color1=[1,1,0], color2=[.6,.6,0])
    ]
    SPHERE_MATS = [
        _create_checkerboard_mat(name="sph_r", color1=[1,0,0], color2=[.6,0,0], offset_u=0.05),
        _create_checkerboard_mat(name="sph_g", color1=[0,1,0], color2=[0,.6,0], offset_u=0.05),
        _create_checkerboard_mat(name="sph_b", color1=[0,0,1], color2=[0,0,.6], offset_u=0.05),
        _create_checkerboard_mat(name="sph_y", color1=[1,1,0], color2=[.6,.6,0], offset_u=0.05)
    ]
    BOX_MATS = [
        _create_mat(name="box_r", color=[1,0,0]),
        _create_mat(name="box_g", color=[0,1,0]),
        _create_mat(name="box_b", color=[0,0,1]),
        _create_mat(name="box_y", color=[1,1,0])
    ]


# Helper Parsers & Converters
def _parse_float(elem, verbose=False):
    if elem is not None and elem is not -1:
        return float(elem)
    else:
        if verbose:
            print("Couldn't parse float element {}...".format(elem))
        return None

def _parse_multi_float(elem):
    if elem is not None and elem is not -1:
        text = elem if isinstance(elem, str) else elem.text
        return [ float(x) for x in text.split(" ") ]
    else:
        return None

def _convert_urdf_dist(u_distance, is_size = True):
    if u_distance is not None:
        return u_distance * SPACE_RATIO_URDF_TO_MAYA
    else:
        return None

def _convert_urdf_vector(u_xyz, is_size = True):
    if u_xyz is not None:
        return [_convert_urdf_dist(c, is_size=is_size) for c in u_xyz]
    else:
        return None

def _convert_urdf_rotation(u_rpy):
    if u_rpy is not None:
        return [degrees(c) for c in u_rpy]
    else:
        return None

def _parse_and_convert_transform(elem):
    if elem is not None and elem is not -1:
        u_xyz = _parse_multi_float( elem.get("xyz") )
        u_rpy = _parse_multi_float( elem.get("rpy") )

        m_translation = _convert_urdf_vector(u_xyz, is_size = False)
        m_rotation = _convert_urdf_rotation(u_rpy)
        return {"t": m_translation, "ro": m_rotation}
    else:
        return None


# Maya Helpers
def _get_joint(name):
    """Get joint with given name / geo name

    Args:
        name (str): Basename or geo name (ex. "chest" or "geo:chest")

    Returns:
        str: Name of joint to look for (ex. "skel:chest")
    """
    basename = name.partition("geo:")[2]
    return "skel:" + basename

def _get_geo(name):
    """Get geo with given name / joint name

    Args:
        name (str): Basename or joint name (ex. "chest" or "skel:chest")

    Returns:
        str: Name of geo to look for (ex. "geo:chest")
    """
    basename = name.partition("skel:")[2]
    return "geo:" + basename

def _create_checkerboard_mat(name="mat", color1=[1,1,1], color2=[0,0,0], tiling_u=1.0, tiling_v=1.0, offset_u =0.0):
    """Create checkerboard material

    Returns:
        str: Maya shading group node name
    """
    cmd.select(clear=True) # Deselect

    # Create lambert material
    mat = cmd.shadingNode("lambert", asShader=True, name=name)
    # Needs a shading group too I guess
    shading_group_node = cmd.sets(name=name + "SG", renderable=True, noSurfaceShader=True, empty=True)
    cmd.connectAttr(mat + ".outColor", shading_group_node + ".surfaceShader", force=True)

    # Create checkerboard texture
    checker_node = cmd.shadingNode("checker", asTexture=True)
    place_tex_node = cmd.shadingNode("place2dTexture", asUtility=True)
    cmd.connectAttr( place_tex_node + ".outUV", checker_node + ".uv", force=True )
    cmd.connectAttr( place_tex_node + ".outUvFilterSize", checker_node + ".uvFilterSize", force=True )
    cmd.connectAttr( checker_node + ".outColor", mat + ".color", force=True )

    # Set colors and tiling
    cmd.setAttr( checker_node + ".color1", *color1, type="double3" )
    cmd.setAttr( checker_node + ".color2", *color2, type="double3" )
    cmd.setAttr( place_tex_node + ".repeatU", tiling_u )
    cmd.setAttr( place_tex_node + ".repeatV", tiling_v )

    # Offset UVs to put checker line on center
    cmd.setAttr( place_tex_node + ".offsetU", offset_u )

    cmd.select(clear=True) # Deselect

    return mat
    #return shading_group_node # Return shading group because that's what we'll need in order to assign mats, not the mat itself

def _create_mat(name="mat", color=[1,1,1]):
    """Create basic material

    Returns:
        str: Maya shading group node name
    """
    cmd.select(clear=True) # Deselect

    # Create lambert material
    mat = cmd.shadingNode("lambert", asShader=True, name=name)
    # Needs a shading group too I guess
    shading_group_node = cmd.sets(name=name + "SG", renderable=True, noSurfaceShader=True, empty=True)
    cmd.connectAttr(mat + ".outColor", shading_group_node + ".surfaceShader", force=True)

    # Set color
    cmd.setAttr( mat + ".color", *color, type="double3" )

    cmd.select(clear=True) # Deselect

    return mat



# For Display
def _tabulate(rows, headers=None):
    """Makes a pretty-looking table.
    (My tabulate version didn't work with Maya's old-ass python version)

    Args:
        rows (list of lists): Rows of elements to be shown as a table.
        headers (list of strs, optional): Headers to be shown above rows.
                                            Can't be greater length than the longest 'rows' sublist. Defaults to None.

    Returns:
        str: Pretty-looking table that you can print out
    """
    lens = []
    n_col = max([len(row) for row in rows])

    # Get headers lengths
    len_headers = [ len(str(h)) for h in headers ] if headers else [0 for _ in range(n_col)]
    for _ in range(n_col - len(len_headers)):
        len_headers.append(0)

    # Get rows lengths
    len_row_elems = []
    for row in rows:
        len_elems = []
        for col_i in range(n_col):
            if col_i < len(row) and row[col_i]:
                len_elem = len(str(row[col_i]))
            else:
                len_elem = 0
            len_elems.append(len_elem)
        len_row_elems.append(len_elems)
    
    # Get column lengths
    len_cols = []
    for col_i in range(n_col):
        len_col = max([l_e[col_i] if col_i < len(l_e) else 0 for l_e in len_row_elems])
        len_cols.append(len_col + 2)

    # BUILD STRING
    # Start with headers
    string = ""
    if headers:
        string += "".join([str(headers[c]) + " "*(len_cols[c] - len_headers[c]) for c in range(n_col)])
        string += "\n"

    # Divider Line
    string += "-"*sum(len_cols)

    # Rows
    for row_i, row in enumerate(rows):
        string += "\n" + "".join([str(row[c]) + " "*(len_cols[c] - len_row_elems[row_i][c]) for c in range(n_col)])

    return string


if __name__ in ("__main__", "__builtin__"):
    build_urdf(DEFAULT_URDF_PATH)