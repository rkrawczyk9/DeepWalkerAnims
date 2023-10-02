# DeepWalkerAnims

## Overview

These scripts help convert animation data to URDF-friendly format. This is to directly support my main repo [DeepWalker](https://github.com/rkrawczyk9/DeepWalker).

The main interesting thing here is maya_urdf\maya_build_urdf.py. This is a URDF converter - it makes your robot in Maya. This is useful because it aallows us to retarget animation onto our robot using the best and easiest methods that DCCs like Maya have to offer.

Note that not everything necessary to this process is driven by scripts... YET! Until that happens (PySide, etc.) a couple steps do involve actually doing stuff in Maya with HumanIK. Not much, but enough that I should eventually lay out some instructions so people can try it. Once this project gets closer to completion I'll flesh out some real documentation. For now, just having fun.

## Contact Me
robertAnimTech@gmail.com
