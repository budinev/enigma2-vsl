import errno
import xml.etree.ElementTree

from enigma import addFont, eLabel, ePixmap, ePoint, eRect, eSize, eWidget, eWindow, eWindowStyleManager, eWindowStyleSkinned, getDesktop, gFont, getFontFaces, gRGB, BT_ALPHATEST, BT_ALPHABLEND, BT_HALIGN_CENTER, BT_HALIGN_LEFT, BT_HALIGN_RIGHT, BT_KEEP_ASPECT_RATIO, BT_SCALE, BT_VALIGN_BOTTOM, BT_VALIGN_CENTER, BT_VALIGN_TOP
from os.path import basename, dirname, isfile

from Components.config import ConfigSubsection, ConfigText, config
from Components.RcModel import rc_model
from Components.Sources.Source import ObsoleteSource
from Components.SystemInfo import BoxInfo
from Tools.Directories import SCOPE_CURRENT_LCDSKIN, SCOPE_CURRENT_SKIN, SCOPE_FONTS, SCOPE_SKIN, resolveFilename
from Tools.Import import my_import
from Tools.LoadPixmap import LoadPixmap

DEFAULT_SKIN = BoxInfo.getItem("HasFullHDSkinSupport") and "pDreamy-FHD/skin.xml" or "PLi-HD/skin.xml"  # SD hardware is no longer supported by the default skin.
EMERGENCY_SKIN = "skin_default/skin.xml"
EMERGENCY_NAME = "Stone II"
DEFAULT_DISPLAY_SKIN = "skin_default/skin_display.xml"
USER_SKIN = "skin_user.xml"
USER_SKIN_TEMPLATE = "skin_user_%s.xml"
SUBTITLE_SKIN = "skin_subtitles.xml"

GUI_SKIN_ID = 0  # Main frame-buffer.
DISPLAY_SKIN_ID = 1  # Front panel / display / LCD.

domScreens = {}  # Dictionary of skin based screens.
colors = {  # Dictionary of skin color names.
	"key_back": gRGB(0x00313131),
	"key_blue": gRGB(0x0018188b),
	"key_green": gRGB(0x001f771f),
	"key_red": gRGB(0x009f1313),
	"key_text": gRGB(0x00ffffff),
	"key_yellow": gRGB(0x00a08500)
}
BodyFont = ("Regular", 20, 24, 18) # font which is used when a font alias definition is missing from the "fonts" dict.
fonts = {  # Dictionary of predefined and skin defined font aliases.
	"Body": BodyFont
}
menus = {}  # Dictionary of images associated with menu entries.
menuicons = {}  # Dictionary of icons associated with menu items.
parameters = {}  # Dictionary of skin parameters used to modify code behavior.
screens = {}  # Dictionary of images associated with screen entries.
setups = {}  # Dictionary of images associated with setup menus.
switchPixmap = {}  # Dictionary of switch images.
windowStyles = {}  # Dictionary of window styles for each screen ID.

config.skin = ConfigSubsection()
skin = resolveFilename(SCOPE_SKIN, DEFAULT_SKIN)
if not isfile(skin):
	print("[Skin] Error: Default skin '%s' is not readable or is not a file!  Using emergency skin." % skin)
	DEFAULT_SKIN = EMERGENCY_SKIN
config.skin.primary_skin = ConfigText(default=DEFAULT_SKIN)
config.skin.display_skin = ConfigText(default=DEFAULT_DISPLAY_SKIN)

currentPrimarySkin = None
currentDisplaySkin = None
onLoadCallbacks = []
runCallbacks = False

# Skins are loaded in order of priority.  Skin with highest priority is
# loaded last.  This is usually the user-specified skin.  In this way
# any duplicated screens will be replaced by a screen of the same name
# with a higher priority.
#
# GUI skins are saved in the settings file as the path relative to
# SCOPE_SKIN.  The full path is NOT saved.  E.g. "MySkin/skin.xml"
#
# Display skins are saved in the settings file as the path relative to
# SCOPE_CURRENT_LCDSKIN.  The full path is NOT saved.
# E.g. "MySkin/skin_display.xml"
#


def InitSkins():
	global currentPrimarySkin, currentDisplaySkin, runCallbacks
	# Add the emergency skin.  This skin should provide enough functionality
	# to enable basic GUI functions to work.
	loadSkin(EMERGENCY_SKIN, scope=SCOPE_CURRENT_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID)
	# Add the subtitle skin.
	loadSkin(SUBTITLE_SKIN, scope=SCOPE_CURRENT_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID)
	# Add the front panel / display / lcd skin.
	result = []
	for skin, name in [(config.skin.display_skin.value, "current"), (DEFAULT_DISPLAY_SKIN, "default")]:
		if skin in result:  # Don't try to add a skin that has already failed.
			continue
		config.skin.display_skin.value = skin
		if loadSkin(config.skin.display_skin.value, scope=SCOPE_CURRENT_LCDSKIN, desktop=getDesktop(DISPLAY_SKIN_ID), screenID=DISPLAY_SKIN_ID):
			currentDisplaySkin = config.skin.display_skin.value
			break
		print("[Skin] Error: Adding %s display skin '%s' has failed!" % (name, config.skin.display_skin.value))
		result.append(skin)
	# Add the main GUI skin.
	result = []
	for skin, name in [(config.skin.primary_skin.value, "current"), (DEFAULT_SKIN, "default")]:
		if skin in result:  # Don't try to add a skin that has already failed.
			continue
		config.skin.primary_skin.value = skin
		if loadSkin(config.skin.primary_skin.value, scope=SCOPE_CURRENT_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID):
			currentPrimarySkin = config.skin.primary_skin.value
			break
		print("[Skin] Error: Adding %s GUI skin '%s' has failed!" % (name, config.skin.primary_skin.value))
		result.append(skin)
	# Add an optional skin related user skin "user_skin_<SkinName>.xml".  If there is
	# not a skin related user skin then try to add am optional generic user skin.
	result = None
	if isfile(resolveFilename(SCOPE_SKIN, config.skin.primary_skin.value)):
		name = USER_SKIN_TEMPLATE % dirname(config.skin.primary_skin.value)
		if isfile(resolveFilename(SCOPE_CURRENT_SKIN, name)):
			result = loadSkin(name, scope=SCOPE_CURRENT_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID)
	if result is None:
		loadSkin(USER_SKIN, scope=SCOPE_CURRENT_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID)
	if not runCallbacks:
		runCallbacks = True
		for method in onLoadCallbacks:
			if callable(method):
				method()

# Temporary entry point for older versions of StartEnigma.py.
#


def loadSkinData(desktop):
	InitSkins()

# Method to load a skin XML file into the skin data structures.
#


def loadSkin(filename, scope=SCOPE_SKIN, desktop=getDesktop(GUI_SKIN_ID), screenID=GUI_SKIN_ID):
	global windowStyles
	filename = resolveFilename(scope, filename)
	print("[Skin] Loading skin file '%s'." % filename)
	try:
		with open(filename, "r") as fd:  # This open gets around a possible file handle leak in Python's XML parser.
			try:
				domSkin = xml.etree.ElementTree.parse(fd).getroot()
				# print("[Skin] DEBUG: Extracting non screen blocks from '%s'.  (scope='%s')" % (filename, scope))
				# For loadSingleSkinData colors, bordersets etc. are applied one after
				# the other in order of ascending priority.
				loadSingleSkinData(desktop, screenID, domSkin, filename, scope=scope)
				for element in domSkin:
					if element.tag == "screen":  # Process all screen elements.
						name = element.attrib.get("name", None)
						if name:  # Without a name, it's useless!
							scrnID = element.attrib.get("id", None)
							if scrnID is None or scrnID == screenID:  # If there is a screen ID is it for this display.
								# print("[Skin] DEBUG: Extracting screen '%s' from '%s'.  (scope='%s')" % (name, filename, scope))
								domScreens[name] = (element, "%s/" % dirname(filename))
					elif element.tag == "windowstyle":  # Process the windowstyle element.
						scrnID = element.attrib.get("id", None)
						if scrnID is not None:  # Without an scrnID, it is useless!
							scrnID = int(scrnID)
							# print("[Skin] DEBUG: Processing a windowstyle ID='%s'." % scrnID)
							domStyle = xml.etree.ElementTree.ElementTree(xml.etree.ElementTree.Element("skin"))
							domStyle.getroot().append(element)
							windowStyles[scrnID] = (desktop, screenID, domStyle.getroot(), filename, scope)
					# Element is not a screen or windowstyle element so no need for it any longer.
				reloadWindowStyles()  # Reload the window style to ensure all skin changes are taken into account.
				print("[Skin] Loading skin file '%s' complete." % filename)
				return True
			except xml.etree.ElementTree.ParseError as err:
				fd.seek(0)
				content = fd.readlines()
				line, column = err.position
				print("[Skin] XML Parse Error: '%s' in '%s'!" % (err, filename))
				data = content[line - 1].replace("\t", " ").rstrip()
				print("[Skin] XML Parse Error: '%s'" % data)
				print("[Skin] XML Parse Error: '%s^%s'" % ("-" * column, " " * (len(data) - column - 1)))
			except Exception as err:
				print("[Skin] Error: Unable to parse skin data in '%s' - '%s'!" % (filename, err))
	except (IOError, OSError) as err:
		if err.errno == errno.ENOENT:  # No such file or directory
			print("[Skin] Warning: Skin file '%s' does not exist!" % filename)
		else:
			print("[Skin] Error %d: Opening skin file '%s'! (%s)" % (err.errno, filename, err.strerror))
	except Exception as err:
		print("[Skin] Error: Unexpected error opening skin file '%s'! (%s)" % (filename, err))
	return False


def reloadSkins():
	global domScreens, colors, fonts, menus, menuicons, parameters, screens, setups, switchPixmap
	domScreens.clear()
	colors.clear()
	colors = {
		"key_back": gRGB(0x00313131),
		"key_blue": gRGB(0x0018188b),
		"key_green": gRGB(0x001f771f),
		"key_red": gRGB(0x009f1313),
		"key_text": gRGB(0x00ffffff),
		"key_yellow": gRGB(0x00a08500)
	}
	fonts.clear()
	fonts = {
		"Body": BodyFont
	}
	menus.clear()
	menuicons.clear()
	parameters.clear()
	screens.clear()
	setups.clear()
	switchPixmap.clear()
	InitSkins()


def addCallback(callback):
	if callback not in onLoadCallbacks:
		onLoadCallbacks.append(callback)


def removeCallback(callback):
	if callback in onLoadCallbacks:
		onLoadCallbacks.remove(callback)


class SkinError(Exception):
	def __init__(self, message):
		self.msg = message

	def __str__(self):
		return "[Skin] {%s}: %s!  Please contact the skin's author!" % (config.skin.primary_skin.value, self.msg)

# Convert a coordinate string into a number.  Used to convert object position and
# size attributes into a number.
#    s is the input string.
#    e is the the parent object size to do relative calculations on parent
#    size is the size of the object size (e.g. width or height)
#    font is a font object to calculate relative to font sizes
# Note some constructs for speeding up simple cases that are very common.
#
# Can do things like:  10+center-10w+4%
# To center the widget on the parent widget,
#    but move forward 10 pixels and 4% of parent width
#    and 10 character widths backward
# Multiplication, division and subexpressions are also allowed: 3*(e-c/2)
#
# Usage:  center : Center the object on parent based on parent size and object size.
#         e      : Take the parent size/width.
#         c      : Take the center point of parent size/width.
#         %      : Take given percentage of parent size/width.
#         w      : Multiply by current font width. (Only to be used in elements where the font attribute is available, i.e. not "None")
#         h      : Multiply by current font height. (Only to be used in elements where the font attribute is available, i.e. not "None")
#         f      : Replace with getSkinFactor().
#


def parseCoordinate(s, e, size=0, font=None, scale=(1, 1)):
	orig = s = s.strip()
	if s.isdigit():  # For speed try a simple number first as these are the most common.
		val = int(s)
	elif s == "center":  # For speed as this can be common case.
		return 0 if not size else (e - size) // 2
	elif s == "e":
		return e
	elif s == "*":
		return None
	else:
		if scale[0] != scale[1]:
			e *= scale[1] / scale[0]
			size *= scale[1] / scale[0]
		if font is None and ("w" in s or "h" in s):
			print("[Skin] Error: 'w' or 'h' is being used in a field where neither is valid. Input string: '%s'" % orig)
			return 0
		# No test on "e" because it's already a variable
		if "center" in s:
			center = (e - size) / 2  # noqa: F841
		if "c" in s:
			c = e / 2  # noqa: F841 do not remove c variable
		if "w" in s:
			s = s.replace("w", "*w")
			w = float(fonts[font][3] * scale[1] / scale[0] if font in fonts else 0)  # noqa: F841
		if "h" in s:
			s = s.replace("h", "*h")
			h = float(fonts[font][2] * scale[1] / scale[0] if font in fonts else 0)  # noqa: F841
		if "%" in s:
			s = s.replace("%", "*e / 100")  # noqa: F841
		if "f" in s:
			f = getSkinFactor() if scale[0] == scale[1] else 1  # noqa: F841, only use getSkinFactor when screen.scale attribute is not present
		# Don't bother trying an int() conversion,
		# because at this point that's almost certainly
		# going to throw an exception.
		try:  # protects against junk in the input
			val = eval(s)
		except Exception as err:
			print("[Skin] %s '%s': Coordinate '%s', processed to '%s', cannot be evaluated!" % (type(err).__name__, err, orig, s))
			val = 0
	# print("[Skin] DEBUG: parseCoordinate s='%s', e='%s', size=%s, font='%s', val='%s', scale='%s'." % (s, e, size, font, val, str(scale)))
	return int(val * scale[0] / scale[1] if scale[0] != scale[1] else val)


def getParentSize(object, desktop):
	if object:
		parent = object.getParent()
		# For some widgets (e.g. ScrollLabel) the skin attributes are applied to a
		# child widget, instead of to the widget itself.  In that case, the parent
		# we have here is not the real parent, but it is the main widget.  We have
		# to go one level higher to get the actual parent.  We can detect this
		# because the 'parent' will not have a size yet.  (The main widget's size
		# will be calculated internally, as soon as the child widget has parsed the
		# skin attributes.)
		if parent and parent.size().isEmpty():
			parent = parent.getParent()
		if parent:
			return parent.size()
		elif desktop:
			return desktop.size()  # Widget has no parent, use desktop size instead for relative coordinates.
	return eSize()


def parseValuePair(s, scale, object=None, desktop=None, size=None):
	x, y = s.split(",")
	parentsize = eSize()
	if object and ("c" in x or "c" in y or "e" in x or "e" in y or "%" in x or "%" in y):  # Need parent size for ce%
		parentsize = getParentSize(object, desktop)
	xval = parseCoordinate(x, parentsize.width(), size and size.width() or 0)
	yval = parseCoordinate(y, parentsize.height(), size and size.height() or 0)
	return (xval * scale[0][0] // scale[0][1], yval * scale[1][0] // scale[1][1])


def parsePosition(s, scale, object=None, desktop=None, size=None):
	return ePoint(*parseValuePair(s, scale, object, desktop, size))

def parseRadius(value):
	data = [x.strip() for x in value.split(";")]
	if len(data) == 2:
		edges = [x.strip() for x in data[1].split(",")]
		edgesMask = {
			"topLeft": eWidget.RADIUS_TOP_LEFT,
			"topRight": eWidget.RADIUS_TOP_RIGHT,
			"top": eWidget.RADIUS_TOP,
			"bottomLeft": eWidget.RADIUS_BOTTOM_LEFT,
			"bottomRight": eWidget.RADIUS_BOTTOM_RIGHT,
			"bottom": eWidget.RADIUS_BOTTOM,
			"left": eWidget.RADIUS_LEFT,
			"right": eWidget.RADIUS_RIGHT,
		}
		edgeValue = 0
		for e in edges:
			edgeValue += edgesMask.get(e, 0)
		return int(data[0]), edgeValue
	else:
		return int(data[0]), eWidget.RADIUS_ALL

def parseSize(s, scale, object=None, desktop=None):
	return eSize(*[max(0, x) for x in parseValuePair(s, scale, object, desktop)])


def parseFont(s, scale=((1, 1), (1, 1))):
	if ";" in s:
		name, size = s.split(";")
		orig = size
		try:
			size = int(size)
		except ValueError:
			try:
				size = size.replace("f", str(getSkinFactor()))
				size = int(eval(size))
			except Exception as err:
				print("[Skin] %s '%s': font size formula '%s', processed to '%s', cannot be evaluated!" % (type(err).__name__, err, orig, s))
				size = 0
	else:
		name = s
		size = 0
	try:
		f = fonts[name]
		name = f[0]
		size = f[1] if size == 0 else size
	except KeyError:
		if name not in getFontFaces():
			f = fonts["Body"]
			print("[Skin] Error: Font '%s' (in '%s') is not defined!  Using 'Body' font ('%s') instead." % (name, s, f[0]))
			name = f[0]
			size = f[1] if size == 0 else size
	return gFont(name, size * scale[0][0] // scale[0][1])


def parseColor(s):
	if s[0] != "#":
		try:
			return colors[s]
		except KeyError:
			raise SkinError("Color '%s' must be #aarrggbb or valid named color" % s)
	return gRGB(int(s[1:], 0x10))


def parseParameter(s):
	"""This function is responsible for parsing parameters in the skin, it can parse integers, floats, hex colors, hex integers, named colors, fonts and strings."""
	if s[0] == "*":  # String.
		return s[1:]
	elif s[0] == "#":  # HEX Color.
		return int(s[1:], 16)
	elif s[:2] == "0x":  # HEX Integer.
		return int(s, 16)
	elif "." in s:  # Float number.
		return float(s)
	elif s in colors:  # Named color.
		return colors[s].argb()
	elif s.find(";") != -1:  # Font.
		font, size = [x.strip() for x in s.split(";", 1)]
		return [font, parseScale(size)]
	else:  # Integer.
		return parseScale(s)


def parseScale(s):
	orig = s
	try:
		val = int(s)
	except ValueError:
		f = getSkinFactor()  # noqa: F841
		try:
			val = int(eval(s))
		except Exception as err:
			print("[Skin] parseScale: %s '%s': formula '%s' cannot be evaluated!" % (type(err).__name__, err, s))
			val = 0
	return val


def mergeScale(s1, s2):
	#  merge ((w, w), (h, h)) with ((x, x), (y, y))
	return ((s1[0][0] * s2[0][0], s1[0][1] * s2[0][1]), (s1[1][0] * s2[1][0], s1[1][1] * s2[1][1]))


def loadPixmap(path, desktop, width=0, height=0):
	option = path.find("#")
	if option != -1:
		path = path[:option]
	if not rc_model.rcIsDefault() and basename(path) in ("rc.png", "rc0.png", "rc1.png", "rc2.png", "oldrc.png"):
		path = rc_model.getRcImg()
	pixmap = LoadPixmap(path, desktop, None, width, height)
	if pixmap is None:
		raise SkinError("Pixmap file '%s' not found" % path)
	return pixmap


def collectAttributes(skinAttributes, node, context, skinPath=None, ignore=(), filenames=frozenset(("pixmap", "pointer", "seek_pointer", "backgroundPixmap", "selectionPixmap", "selectionPixmapLarge", "sliderPixmap", "scrollbarSliderPicture", "scrollbarbackgroundPixmap", "scrollbarBackgroundPicture"))):
	size = None
	pos = None
	font = None
	for attrib, value in node.items():  # Walk all attributes.
		if attrib not in ignore:
			if attrib in filenames:
				value = resolveFilename(SCOPE_CURRENT_SKIN, value, path_prefix=skinPath)
			# Bit of a hack this, really.  When a window has a flag (e.g. wfNoBorder)
			# it needs to be set at least before the size is set, in order for the
			# window dimensions to be calculated correctly in all situations.
			# If wfNoBorder is applied after the size has been set, the window will
			# fail to clear the title area.  Similar situation for a scrollbar in a
			# listbox; when the scrollbar setting is applied after the size, a scrollbar
			# will not be shown until the selection moves for the first time.
			if attrib == "size":
				size = value
			elif attrib == "position":
				pos = value
			elif attrib == "font":
				font = value
				skinAttributes.append((attrib, font))
			else:
				skinAttributes.append((attrib, value))
	if pos is not None:
		pos, size = context.parse(pos, size, font)
		skinAttributes.append(("position", pos))
	if size is not None:
		skinAttributes.append(("size", size))


class AttributeParser:
	def __init__(self, guiObject, desktop, scale=((1, 1), (1, 1))):
		self.guiObject = guiObject
		self.desktop = desktop
		self.scaleTuple = scale

	def applyOne(self, attrib, value):
		try:
			getattr(self, attrib)(value)
		except AttributeError:
			print("[Skin] Attribute '%s' (with value of '%s') in object of type '%s' is not implemented!" % (attrib, value, self.guiObject.__class__.__name__))
		except SkinError as err:
			print("[Skin] Error: %s" % str(err))
		except Exception:
			print("[Skin] Attribute '%s' with wrong (or unknown) value '%s' in object of type '%s'!" % (attrib, value, self.guiObject.__class__.__name__))

	def applyAll(self, attrs):
		attrs.sort(key=lambda a: {"pixmap": 1, "scale": -1}.get(a[0], 0))  # For svg pixmap scale required the size, so sort pixmap last (and scale first)

		# if skin attribute "screen.resolution" is set, graphics should be scaled, so force that here
		if attrs and attrs[-1][0] == "pixmap" and (self.scaleTuple[0][0] != self.scaleTuple[0][1] or self.scaleTuple[1][0] != self.scaleTuple[1][1]) and attrs[0][0] != "scale":
			attrs.insert(0, ("scale", "1"))

		for attrib, value in attrs:
			self.applyOne(attrib, value)

	def applyHorizontalScale(self, value):
		return int(value) if self.scaleTuple[0][0] == self.scaleTuple[0][1] else int(int(value) * self.scaleTuple[0][0] / self.scaleTuple[0][1])

	def applyVerticalScale(self, value):
		return int(value) if self.scaleTuple[0][0] == self.scaleTuple[0][1] else int(int(value) * self.scaleTuple[1][0] / self.scaleTuple[1][1])

	def conditional(self, value):
		pass

	def objectTypes(self, value):
		pass

	def position(self, value):
		self.guiObject.move(ePoint(*value) if isinstance(value, tuple) else parsePosition(value, self.scaleTuple, self.guiObject, self.desktop, self.guiObject.csize()))

	def size(self, value):
		self.guiObject.resize(eSize(*value) if isinstance(value, tuple) else parseSize(value, self.scaleTuple, self.guiObject, self.desktop))

	def animationPaused(self, value):
		pass

# OpenPLi is missing the C++ code to support this animation method.
#
# 	def animationMode(self, value):
# 		try:
# 			self.guiObject.setAnimationMode({
# 				"disable": 0x00,
# 				"off": 0x00,
# 				"offshow": 0x10,
# 				"offhide": 0x01,
# 				"onshow": 0x01,
# 				"onhide": 0x10,
# 				"disable_onshow": 0x10,
# 				"disable_onhide": 0x01
# 			}[value])
# 		except KeyError:
# 			print("[Skin] Error: Invalid animationMode '%s'!  Must be one of 'disable', 'off', 'offshow', 'offhide', 'onshow' or 'onhide'." % value)

	def title(self, value):
		self.guiObject.setTitle(_(value))

	def text(self, value):
		self.guiObject.setText(_(value))

	def font(self, value):
		self.guiObject.setFont(parseFont(value, self.scaleTuple))

	def secondfont(self, value):
		self.guiObject.setSecondFont(parseFont(value, self.scaleTuple))
		
	def widgetBorderColor(self, value):
		self.guiObject.setWidgetBorderColor(parseColor(value))

	def widgetBorderWidth(self, value):
		self.guiObject.setWidgetBorderWidth(self.applyVerticalScale(parseScale(value)))

	def zPosition(self, value):
		self.guiObject.setZPosition(int(value))

	def itemHeight(self, value):
		self.guiObject.setItemHeight(self.applyVerticalScale(parseScale(value)))

	def itemWidth(self, value):
		self.guiObject.setItemWidth(self.applyHorizontalScale(parseScale(value)))

	def itemCornerRadius(self, value):
		radius, edgeValue = parseRadius(value)
		self.guiObject.setItemCornerRadius(radius, edgeValue)

	def itemCornerRadiusSelected(self, value):
		radius, edgeValue = parseRadius(value)
		self.guiObject.setItemCornerRadiusSelected(radius, edgeValue)

	def pixmap(self, value):
		if value.endswith(".svg"): # if graphic is svg force alphatest to "blend"
			self.guiObject.setAlphatest(BT_ALPHABLEND)
		self.guiObject.setPixmap(loadPixmap(value, self.desktop, self.guiObject.size().width(), self.guiObject.size().height()))

	def backgroundPixmap(self, value):
		self.guiObject.setBackgroundPicture(loadPixmap(value, self.desktop))

	def selectionPixmap(self, value):
		self.guiObject.setSelectionPicture(loadPixmap(value, self.desktop))

	def selectionPixmapLarge(self, value):
		self.guiObject.setSelectionPictureLarge(loadPixmap(value, self.desktop))

	def sliderPixmap(self, value):
		self.guiObject.setSliderPicture(loadPixmap(value, self.desktop))

	def scrollbarbackgroundPixmap(self, value):
		self.guiObject.setScrollbarBackgroundPicture(loadPixmap(value, self.desktop))

	def scrollbarSliderPicture(self, value):  # For compatibility same as sliderPixmap.
		self.guiObject.setSliderPicture(loadPixmap(value, self.desktop))

	def scrollbarBackgroundPicture(self, value):  # For compatibility same as scrollbarbackgroundPixmap.
		self.guiObject.setScrollbarBackgroundPicture(loadPixmap(value, self.desktop))

	def alphatest(self, value):
		try:
			self.guiObject.setAlphatest({
				"on": BT_ALPHATEST,
				"off": 0,
				"blend": BT_ALPHABLEND
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid alphatest '%s'!  Must be one of 'on', 'off' or 'blend'." % value)

	def scale(self, value):
		value = 1 if value.lower() in ("1", "enabled", "on", "scale", "true", "yes") else 0
		self.guiObject.setScale(value)

	def scaleFlags(self, value):
		base = BT_SCALE | BT_KEEP_ASPECT_RATIO
		try:
			self.guiObject.setPixmapScale({
				"none": 0,
				"scale": BT_SCALE,
				"scaleKeepAspect": base,
				"scaleLeftTop": base | BT_HALIGN_LEFT | BT_VALIGN_TOP,
				"scaleLeftCenter": base | BT_HALIGN_LEFT | BT_VALIGN_CENTER,
				"scaleLeftBottom": base | BT_HALIGN_LEFT | BT_VALIGN_BOTTOM,
				"scaleCenterTop": base | BT_HALIGN_CENTER | BT_VALIGN_TOP,
				"scaleCenter": base | BT_HALIGN_CENTER | BT_VALIGN_CENTER,
				"scaleCenterBottom": base | BT_HALIGN_CENTER | BT_VALIGN_BOTTOM,
				"scaleRightTop": base | BT_HALIGN_RIGHT | BT_VALIGN_TOP,
				"scaleRightCenter": base | BT_HALIGN_RIGHT | BT_VALIGN_CENTER,
				"scaleRightBottom": base | BT_HALIGN_RIGHT | BT_VALIGN_BOTTOM,
				"moveLeftTop": BT_HALIGN_LEFT | BT_VALIGN_TOP,
				"moveLeftCenter": BT_HALIGN_LEFT | BT_VALIGN_CENTER,
				"moveLeftBottom": BT_HALIGN_LEFT | BT_VALIGN_BOTTOM,
				"moveCenterTop": BT_HALIGN_CENTER | BT_VALIGN_TOP,
				"moveCenter": BT_HALIGN_CENTER | BT_VALIGN_CENTER,
				"moveCenterBottom": BT_HALIGN_CENTER | BT_VALIGN_BOTTOM,
				"moveRightTop": BT_HALIGN_RIGHT | BT_VALIGN_TOP,
				"moveRightCenter": BT_HALIGN_RIGHT | BT_VALIGN_CENTER,
				"moveRightBottom": BT_HALIGN_RIGHT | BT_VALIGN_BOTTOM
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid scale '%s'!  Must be one of 'none', 'scale', 'scaleKeepAspect', 'scaleLeftTop', 'scaleLeftCenter', 'scaleLeftBotton', 'scaleCenterTop', 'scaleCenter', 'scaleCenterBotton', 'scaleRightTop', 'scaleRightCenter', 'scaleRightBottom', 'moveLeftTop', 'moveLeftCenter', 'moveLeftBotton', 'moveCenterTop', 'moveCenter', 'moveCenterBottom', 'moveRightTop', 'moveRightCenter', 'moveRightBottom' ('Center'/'Centre'/'Middle' are equivalent)." % value)

	def orientation(self, value):  # Used by eSlider and eListBox.
		try:
			self.guiObject.setOrientation(*{
				"orVertical": (self.guiObject.orVertical, False),
				"orTopToBottom": (self.guiObject.orVertical, False),
				"orBottomToTop": (self.guiObject.orVertical, True),
				"orHorizontal": (self.guiObject.orHorizontal, False),
				"orLeftToRight": (self.guiObject.orHorizontal, False),
				"orRightToLeft": (self.guiObject.orHorizontal, True)
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid orientation '%s'!  Must be one of 'orVertical', 'orTopToBottom', 'orBottomToTop', 'orHorizontal', 'orLeftToRight' or 'orRightToLeft'." % value)

	def valign(self, value):
		try:
			self.guiObject.setVAlign({
				"top": self.guiObject.alignTop,
				"center": self.guiObject.alignCenter,
				"bottom": self.guiObject.alignBottom
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid valign '%s'!  Must be one of 'top', 'center' or 'bottom'." % value)

	def halign(self, value):
		try:
			self.guiObject.setHAlign({
				"left": self.guiObject.alignLeft,
				"center": self.guiObject.alignCenter,
				"right": self.guiObject.alignRight,
				"block": self.guiObject.alignBlock
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid halign '%s'!  Must be one of 'left', 'center', 'right' or 'block'." % value)

	def textOffset(self, value):
		x, y = value.split(",")
		self.guiObject.setTextOffset(ePoint(int(x) * self.scaleTuple[0][0] // self.scaleTuple[0][1], int(y) * self.scaleTuple[1][0] // self.scaleTuple[1][1]))

	def flags(self, value):
		flags = value.split(",")
		for f in flags:
			try:
				fv = eWindow.__dict__[f]
				self.guiObject.setFlag(fv)
			except KeyError:
				print("[Skin] Error: Invalid flag '%s'!" % f)

	def backgroundColor(self, value):
		self.guiObject.setBackgroundColor(parseColor(value))

	def backgroundColorSelected(self, value):
		self.guiObject.setBackgroundColorSelected(parseColor(value))

	def foregroundColor(self, value):
		self.guiObject.setForegroundColor(parseColor(value))

	def foregroundColorSelected(self, value):
		self.guiObject.setForegroundColorSelected(parseColor(value))

	def foregroundNotCrypted(self, value):
		self.guiObject.setForegroundColor(parseColor(value))

	def backgroundNotCrypted(self, value):
		self.guiObject.setBackgroundColor(parseColor(value))

	def foregroundCrypted(self, value):
		self.guiObject.setForegroundColor(parseColor(value))

	def backgroundCrypted(self, value):
		self.guiObject.setBackgroundColor(parseColor(value))

	def foregroundEncrypted(self, value):
		self.guiObject.setForegroundColor(parseColor(value))

	def backgroundEncrypted(self, value):
		self.guiObject.setBackgroundColor(parseColor(value))

	def shadowColor(self, value):
		self.guiObject.setShadowColor(parseColor(value))

	def selectionDisabled(self, value):
		self.guiObject.setSelectionEnable(0)

	def transparent(self, value):
		self.guiObject.setTransparent(int(value))

	def borderColor(self, value):
		self.guiObject.setBorderColor(parseColor(value))

	def borderWidth(self, value):
		self.guiObject.setBorderWidth(self.applyVerticalScale(parseScale(value)))

	def cornerRadius(self, value):
		radius, edgeValue = parseRadius(value)
		self.guiObject.setCornerRadius(radius, edgeValue)

	def scrollbarSliderBorderWidth(self, value):
		self.guiObject.setScrollbarBorderWidth(self.applyHorizontalScale(parseScale(value)))

	def scrollbarWidth(self, value):
		self.guiObject.setScrollbarWidth(self.applyHorizontalScale(parseScale(value)))

	def scrollbarSliderBorderColor(self, value):
		self.guiObject.setSliderBorderColor(parseColor(value))

	def scrollbarSliderForegroundColor(self, value):
		self.guiObject.setSliderForegroundColor(parseColor(value))

	def scrollbarMode(self, value):
		try:
			self.guiObject.setScrollbarMode({
				"showOnDemand": self.guiObject.showOnDemand,
				"showAlways": self.guiObject.showAlways,
				"showNever": self.guiObject.showNever,
				"showLeft": self.guiObject.showLeft
			}[value])
		except KeyError:
			print("[Skin] Error: Invalid scrollbarMode '%s'!  Must be one of 'showOnDemand', 'showAlways', 'showNever' or 'showLeft'." % value)

	def enableWrapAround(self, value):
		value = True if value.lower() in ("1", "enabled", "enablewraparound", "on", "true", "yes") else False
		self.guiObject.setWrapAround(value)

	def pointer(self, value):
		(name, pos) = value.split(":")
		pos = parsePosition(pos, self.scaleTuple)
		ptr = loadPixmap(name, self.desktop)
		self.guiObject.setPointer(0, ptr, pos)

	def seek_pointer(self, value):
		(name, pos) = value.split(":")
		pos = parsePosition(pos, self.scaleTuple)
		ptr = loadPixmap(name, self.desktop)
		self.guiObject.setPointer(1, ptr, pos)

	def shadowOffset(self, value):
		self.guiObject.setShadowOffset(parsePosition(value, self.scaleTuple))

	def noWrap(self, value):
		value = 1 if value.lower() in ("1", "enabled", "nowrap", "on", "true", "yes") else 0
		self.guiObject.setNoWrap(value)

	def split(self, value):
		pass

	def colposition(self, value):
		pass

	def dividechar(self, value):
		pass

	def resolution(self, value):
		pass


def applySingleAttribute(guiObject, desktop, attrib, value, scale=((1, 1), (1, 1))):
	# Is anyone still using applySingleAttribute?
	AttributeParser(guiObject, desktop, scale).applyOne(attrib, value)


def applyAllAttributes(guiObject, desktop, attributes, scale):
	AttributeParser(guiObject, desktop, scale).applyAll(attributes)


def reloadWindowStyles():
	for screenID in windowStyles:
		desktop, screenID, domSkin, pathSkin, scope = windowStyles[screenID]
		loadSingleSkinData(desktop, screenID, domSkin, pathSkin, scope)


def loadSingleSkinData(desktop, screenID, domSkin, pathSkin, scope=SCOPE_CURRENT_SKIN):
	"""Loads skin data like colors, windowstyle etc."""
	assert domSkin.tag == "skin", "root element in skin must be 'skin'!"
	global colors, fonts, menus, parameters, screens, setups, switchPixmap
	for tag in domSkin.findall("output"):
		scrnID = int(tag.attrib.get("id", GUI_SKIN_ID))
		if scrnID == GUI_SKIN_ID:
			for res in tag.findall("resolution"):
				xres = res.attrib.get("xres")
				xres = int(xres) if xres else 720
				yres = res.attrib.get("yres")
				yres = int(yres) if yres else 576
				bpp = res.attrib.get("bpp")
				bpp = int(bpp) if bpp else 32
				# print("[Skin] DEBUG: Resolution xres=%d, yres=%d, bpp=%d." % (xres, yres, bpp))
				from enigma import gMainDC
				gMainDC.getInstance().setResolution(xres, yres)
				desktop.resize(eSize(xres, yres))
				if bpp != 32:
					pass  # Load palette (Not yet implemented!)

				fonts["Body"] = applySkinFactor(*BodyFont)

				# Only add font aliases here for lists that are not part of enigma2 repo.
				# Font aliases for modules in this repository should be dealt with directly in the corresponding py, not here.
				fonts["Dreamexplorer"] = fonts["Body"]
				fonts["ExpandableList"] = fonts["Body"]
				fonts["ImsSelectionList"] = applySkinFactor("Regular", 22, 30)
				fonts["PartnerBoxBouquetList0"] = applySkinFactor("Regular", 20, 30)
				fonts["PartnerBoxBouquetList1"] = applySkinFactor("Regular", 18)
				fonts["PartnerBoxChannelList0"] = applySkinFactor("Regular", 20, 70)
				fonts["PartnerBoxChannelList1"] = applySkinFactor("Regular", 18)
				fonts["PartnerBoxChannelEPGList0"] = applySkinFactor("Regular", 22, 30)
				fonts["PartnerBoxE2TimerMenu0"] = applySkinFactor("Regular", 20, 70)
				fonts["PartnerBoxE2TimerMenu1"] = applySkinFactor("Regular", 18)
				fonts["PartnerBoxEntryList0"] = applySkinFactor("Regular", 20, 30)
				fonts["PartnerBoxEntryList1"] = applySkinFactor("Regular", 18)

				# Only add parameters here for lists that are not part of enigma2 repo.
				# Parameters for modules in this repository should be dealt with directly in the corresponding py, not here.
				parameters["AutotimerListChannels"] = applySkinFactor(2, 40, 3, 21)
				parameters["AutotimerListDays"] = applySkinFactor(1, 26, 3, 17)
				parameters["AutotimerListHasTimespan"] = applySkinFactor(103, 3, 100, 17)
				parameters["AutotimerListIcon"] = applySkinFactor(2, -1, 24, 24)
				parameters["AutotimerListRectypeicon"] = applySkinFactor(26, 3, 20, 20)
				parameters["AutotimerListTimerName"] = applySkinFactor(50, 3, 18, 21)
				parameters["AutotimerListTimespan"] = applySkinFactor(2, 26, 3, 17)
				parameters["DreamexplorerIcon"] = applySkinFactor(12, 3, 20, 20)
				parameters["DreamexplorerName"] = applySkinFactor(40, 2, 1000, 22)
				parameters["ExpandableListCategory"] = applySkinFactor(45, 0, 655, 25)
				parameters["ExpandableListIcon"] = applySkinFactor(5, 0, 30, 25)
				parameters["ExpandableListItem"] = applySkinFactor(80, 3, 620, 25)
				parameters["ExpandableListLock"] = applySkinFactor(45, 1, 25, 24)
				parameters["PartnerBoxBouquetListName"] = applySkinFactor(0, 0, 30)
				parameters["PartnerBoxChannelListName"] = applySkinFactor(0, 0, 30)
				parameters["PartnerBoxChannelListTime"] = applySkinFactor(0, 50, 150, 20)
				parameters["PartnerBoxChannelListTitle"] = applySkinFactor(0, 30, 20)
				parameters["PartnerBoxE1TimerState"] = applySkinFactor(170, 50, 170, 20)
				parameters["PartnerBoxE1TimerTime"] = applySkinFactor(0, 50, 170, 20)
				parameters["PartnerBoxE2TimerIcon"] = applySkinFactor(510, 5, 20, 20)
				parameters["PartnerBoxE2TimerIconRepeat"] = applySkinFactor(510, 30, 20, 20)
				parameters["PartnerBoxE2TimerState"] = applySkinFactor(150, 50, 150, 20)
				parameters["PartnerBoxE2TimerTime"] = applySkinFactor(0, 50, 150, 20)
				parameters["PartnerBoxEntryListName"] = applySkinFactor(5, 0, 150, 25)
				parameters["PartnerBoxEntryListIP"] = applySkinFactor(120, 0, 150, 25)
				parameters["PartnerBoxEntryListPort"] = applySkinFactor(270, 0, 100, 25)
				parameters["PartnerBoxEntryListType"] = applySkinFactor(410, 0, 100, 25)
				parameters["PartnerBoxTimerName"] = applySkinFactor(0, 30, 20)
				parameters["PartnerBoxTimerServicename"] = applySkinFactor(0, 0, 30)
				parameters["SHOUTcastListItem"] = applySkinFactor(20, 18, 22, 69, 20, 23, 43, 22)

	for tag in domSkin.findall("include"):
		filename = tag.attrib.get("filename")
		if filename:
			filename = resolveFilename(scope, filename, path_prefix=pathSkin)
			if isfile(filename):
				loadSkin(filename, scope=scope, desktop=desktop, screenID=screenID)
			else:
				raise SkinError("Included file '%s' not found" % filename)
	for tag in domSkin.findall("switchpixmap"):
		for pixmap in tag.findall("pixmap"):
			name = pixmap.attrib.get("name")
			if not name:
				raise SkinError("Pixmap needs name attribute")
			filename = pixmap.attrib.get("filename")
			if not filename:
				raise SkinError("Pixmap needs filename attribute")
			resolved = resolveFilename(scope, filename, path_prefix=pathSkin)
			if isfile(resolved):
				switchPixmap[name] = LoadPixmap(resolved, cached=True)
			else:
				raise SkinError("The switchpixmap pixmap filename='%s' (%s) not found" % (filename, resolved))
	for tag in domSkin.findall("colors"):
		for color in tag.findall("color"):
			name = color.attrib.get("name")
			color = color.attrib.get("value")
			if name and color:
				colors[name] = parseColor(color)
				# print("[Skin] DEBUG: Color name='%s', color='%s'." % (name, color))
			else:
				raise SkinError("Tag 'color' needs a name and color, got name='%s' and color='%s'" % (name, color))
	for tag in domSkin.findall("fonts"):
		for font in tag.findall("font"):
			filename = font.attrib.get("filename", "<NONAME>")
			name = font.attrib.get("name", "Regular")
			scale = font.attrib.get("scale")
			scale = int(scale) if scale else 100
			isReplacement = font.attrib.get("replacement") and True or False
			render = font.attrib.get("render")
			if render:
				render = int(render)
			else:
				render = 0
			filename = resolveFilename(SCOPE_FONTS, filename, path_prefix=pathSkin)
			if isfile(filename):
				addFont(filename, name, scale, isReplacement, render)
				# Log provided by C++ addFont code.
				# print("[Skin] Add font: Font path='%s', name='%s', scale=%d, isReplacement=%s, render=%d." % (filename, name, scale, isReplacement, render))
			else:
				raise SkinError("Font file '%s' not found" % filename)
		fallbackFont = resolveFilename(SCOPE_FONTS, "fallback.font", path_prefix=pathSkin)
		if isfile(fallbackFont):
			addFont(fallbackFont, "Fallback", 100, -1, 0)
		# else:  # As this is optional don't raise an error.
		# 	raise SkinError("Fallback font '%s' not found" % fallbackFont)
		for alias in tag.findall("alias"):
			try:
				name = alias.attrib.get("name")
				font = alias.attrib.get("font")
				size = parseScale(alias.attrib.get("size"))
				height = parseScale(alias.attrib.get("height", size))  # To be calculated some day.
				width = parseScale(alias.attrib.get("width", size))  # To be calculated some day.
				fonts[name] = (font, size, height, width)
				# print("[Skin] Add font alias: name='%s', font='%s', size=%d, height=%s, width=%d." % (name, font, size, height, width))
			except Exception as err:
				raise SkinError("Bad font alias: '%s'" % str(err))
	for tag in domSkin.findall("parameters"):
		for parameter in tag.findall("parameter"):
			try:
				name = parameter.attrib.get("name")
				value = parameter.attrib.get("value")
				parameters[name] = list(map(parseParameter, [x.strip() for x in value.split(",")])) if "," in value else parseParameter(value)
			except Exception as err:
				raise SkinError("Bad parameter: '%s'" % str(err))
	for tag in domSkin.findall("menus"):
		for menu in tag.findall("menu"):
			key = menu.attrib.get("key")
			image = menu.attrib.get("image")
			if key and image:
				menus[key] = image
				# print("[Skin] DEBUG: Menu key='%s', image='%s'." % (key, image))
			else:
				raise SkinError("Tag menu needs key and image, got key='%s' and image='%s'" % (key, image))
	for tag in domSkin.findall("menuicons"):
		for menuicon in tag.findall("menuicon"):
			key = menuicon.attrib.get("key")
			image = menuicon.attrib.get("image")
			if key and image:
				menuicons[key] = image
				# print("[Skin] DEBUG: Menu key='%s', image='%s'." % (key, image))
			else:
				raise SkinError("Tag 'menuicon' needs key and image, got key='%s' and image='%s'" % (key, image))
	for tag in domSkin.findall("screens"):
		for screen in tag.findall("screen"):
			key = screen.attrib.get("key")
			image = screen.attrib.get("image")
			if key and image:
				screens[key] = image
				# print("[Skin] DEBUG: Screen key='%s', image='%s'." % (key, image))
			else:
				raise SkinError("Tag 'screen' needs key and image, got key='%s' and image='%s'" % (key, image))
	for tag in domSkin.findall("setups"):
		for setup in tag.findall("setup"):
			key = setup.attrib.get("key")
			image = setup.attrib.get("image")
			if key and image:
				setups[key] = image
				# print("[Skin] DEBUG: Setup key='%s', image='%s'." % (key, image))
			else:
				raise SkinError("Tag setup needs key and image, got key='%s' and image='%s'" % (key, image))
	for tag in domSkin.findall("subtitles"):
		from enigma import eSubtitleWidget
		scale = ((1, 1), (1, 1))
		for substyle in tag.findall("sub"):
			font = parseFont(substyle.attrib.get("font"), scale)
			col = substyle.attrib.get("foregroundColor")
			if col:
				foregroundColor = parseColor(col)
				haveColor = 1
			else:
				foregroundColor = gRGB(0xFFFFFF)
				haveColor = 0
			col = substyle.attrib.get("borderColor")
			if col:
				borderColor = parseColor(col)
			else:
				borderColor = gRGB(0)
			borderwidth = substyle.attrib.get("borderWidth")
			if borderwidth is None:
				borderWidth = 3  # Default: Use a subtitle border.
			else:
				borderWidth = int(borderwidth)
			face = eSubtitleWidget.__dict__[substyle.attrib.get("name")]
			eSubtitleWidget.setFontStyle(face, font, haveColor, foregroundColor, borderColor, borderWidth)
	for tag in domSkin.findall("windowstyle"):
		style = eWindowStyleSkinned()
		scrnID = int(tag.attrib.get("id", GUI_SKIN_ID))
		font = gFont("Regular", 20)  # Default
		offset = eSize(20, 5)  # Default
		for title in tag.findall("title"):
			offset = parseSize(title.attrib.get("offset"), ((1, 1), (1, 1)))
			font = parseFont(title.attrib.get("font"), ((1, 1), (1, 1)))
		style.setTitleFont(font)
		style.setTitleOffset(offset)
		# print("[Skin] DEBUG: WindowStyle font, offset - '%s' '%s'." % (str(font), str(offset)))
		for borderset in tag.findall("borderset"):
			bsName = str(borderset.attrib.get("name"))
			for pixmap in borderset.findall("pixmap"):
				bpName = pixmap.attrib.get("pos")
				filename = pixmap.attrib.get("filename")
				if filename and bpName:
					png = loadPixmap(resolveFilename(scope, filename, path_prefix=pathSkin), desktop)
					try:
						style.setPixmap(eWindowStyleSkinned.__dict__[bsName], eWindowStyleSkinned.__dict__[bpName], png)
					except Exception:
						pass
				# print("[Skin] DEBUG: WindowStyle borderset name, filename - '%s' '%s'." % (bpName, filename))
		for color in tag.findall("color"):
			colorType = color.attrib.get("name")
			color = parseColor(color.attrib.get("color"))
			try:
				style.setColor(eWindowStyleSkinned.__dict__["col" + colorType], color)
			except Exception:
				raise SkinError("Unknown color type '%s'" % colorType)
			# print("[Skin] DEBUG: WindowStyle color type, color -" % (colorType, str(color)))
		x = eWindowStyleManager.getInstance()
		x.setStyle(scrnID, style)
	for tag in domSkin.findall("margin"):
		scrnID = int(tag.attrib.get("id", GUI_SKIN_ID))
		r = eRect(0, 0, 0, 0)
		v = tag.attrib.get("left")
		if v:
			r.setLeft(int(v))
		v = tag.attrib.get("top")
		if v:
			r.setTop(int(v))
		v = tag.attrib.get("right")
		if v:
			r.setRight(int(v))
		v = tag.attrib.get("bottom")
		if v:
			r.setBottom(int(v))
		# The "desktop" parameter is hard-coded to the GUI screen, so we must ask
		# for the one that this actually applies to.
		getDesktop(scrnID).setMargins(r)


class additionalWidget:
	def __init__(self):
		pass


# Class that makes a tuple look like something else. Some plugins just assume
# that size is a string and try to parse it. This class makes that work.
class SizeTuple(tuple):
	def split(self, *args):
		return str(self[0]), str(self[1])

	def strip(self, *args):
		return "%s,%s" % self

	def __str__(self):
		return "%s,%s" % self


class SkinContext:
	def __init__(self, parent=None, pos=None, size=None, font=None):
		if parent is not None and pos is not None:
			pos, size = parent.parse(pos, size, font)
			self.x, self.y = pos
			self.w, self.h = size
			self.scale = parent.scale
		else:
			self.x = None
			self.y = None
			self.w = None
			self.h = None
			self.scale = ((1, 1), (1, 1))

	def __str__(self):
		return "Context (%s,%s)+(%s,%s)" % (self.x, self.y, self.w, self.h)

	def parse(self, pos, size, font):
		if pos == "fill":
			pos = (self.x, self.y)
			size = (self.w, self.h)
			self.w = 0
			self.h = 0
		else:
			w, h = size.split(",")
			w = parseCoordinate(w, self.w, 0, font, self.scale[0])
			h = parseCoordinate(h, self.h, 0, font, self.scale[1])
			if pos == "bottom":
				pos = (self.x, self.y + self.h - h)
				size = (self.w, h)
				self.h -= h
			elif pos == "top":
				pos = (self.x, self.y)
				size = (self.w, h)
				self.h -= h
				self.y += h
			elif pos == "left":
				pos = (self.x, self.y)
				size = (w, self.h)
				self.x += w
				self.w -= w
			elif pos == "right":
				pos = (self.x + self.w - w, self.y)
				size = (w, self.h)
				self.w -= w
			else:
				size = (w, h)
				pos = pos.split(",")
				pos = (self.x + parseCoordinate(pos[0], self.w, size[0], font, self.scale[0]), self.y + parseCoordinate(pos[1], self.h, size[1], font, self.scale[1]))
		return (SizeTuple(pos), SizeTuple(size))


# A context that stacks things instead of aligning them.
#
class SkinContextStack(SkinContext):
	def parse(self, pos, size, font):
		if pos == "fill":
			pos = (self.x, self.y)
			size = (self.w, self.h)
		else:
			w, h = size.split(",")
			w = parseCoordinate(w, self.w, 0, font, self.scale[0])
			h = parseCoordinate(h, self.h, 0, font, self.scale[1])
			if pos == "bottom":
				pos = (self.x, self.y + self.h - h)
				size = (self.w, h)
			elif pos == "top":
				pos = (self.x, self.y)
				size = (self.w, h)
			elif pos == "left":
				pos = (self.x, self.y)
				size = (w, self.h)
			elif pos == "right":
				pos = (self.x + self.w - w, self.y)
				size = (w, self.h)
			else:
				size = (w, h)
				pos = pos.split(",")
				pos = (self.x + parseCoordinate(pos[0], self.w, size[0], font, self.scale[0]), self.y + parseCoordinate(pos[1], self.h, size[1], font, self.scale[1]))
		return (SizeTuple(pos), SizeTuple(size))


def readSkin(screen, skin, names, desktop):
	if not isinstance(names, list):
		names = [names]
	for n in names:  # Try all skins, first existing one has priority.
		myScreen, path = domScreens.get(n, (None, None))
		if myScreen is not None:
			if screen.mandatoryWidgets is None:
				screen.mandatoryWidgets = []
			else:
				widgets = findWidgets(n)
			if screen.mandatoryWidgets == [] or all(item in widgets for item in screen.mandatoryWidgets):
				name = n  # Use this name for debug output.
				break
			else:
				print("[Skin] Warning: Skin screen '%s' rejected as it does not offer all the mandatory widgets '%s'!" % (n, ", ".join(screen.mandatoryWidgets)))
				myScreen = None
	else:
		name = "<embedded-in-%s>" % screen.__class__.__name__
	if myScreen is None:  # Otherwise try embedded skin.
		myScreen = getattr(screen, "parsedSkin", None)
	if myScreen is None and getattr(screen, "skin", None):  # Try uncompiled embedded skin.
		if isinstance(screen.skin, list):
			print("[Skin] Resizable embedded skin template found in '%s'." % name)
			skin = screen.skin[0] % tuple([int(x * getSkinFactor()) for x in screen.skin[1:]])
		else:
			skin = screen.skin
		print("[Skin] Parsing embedded skin '%s'." % name)
		if isinstance(skin, tuple):
			for s in skin:
				candidate = xml.etree.ElementTree.fromstring(s)
				if candidate.tag == "screen":
					screenID = candidate.attrib.get("id", None)
					if (not screenID) or (int(screenID) == DISPLAY_SKIN_ID):
						myScreen = candidate
						break
			else:
				print("[Skin] No suitable screen found!")
		else:
			myScreen = xml.etree.ElementTree.fromstring(skin)
		if myScreen:
			screen.parsedSkin = myScreen
	if myScreen is None:
		print("[Skin] No skin to read or screen to display.")
		myScreen = screen.parsedSkin = xml.etree.ElementTree.fromstring("<screen></screen>")
	screen.skinAttributes = []
	skinPath = getattr(screen, "skin_path", path)
	context = SkinContextStack()
	s = desktop.bounds()
	context.x = s.left()
	context.y = s.top()
	context.w = s.width()
	context.h = s.height()
	resolution = tuple([int(x.strip()) for x in myScreen.attrib.get("resolution", f"{context.w},{context.h}").split(",")])
	context.scale = ((context.w, resolution[0]), (context.h, resolution[1]))
	del s
	collectAttributes(screen.skinAttributes, myScreen, context, skinPath, ignore=("name",))
	context = SkinContext(context, myScreen.attrib.get("position"), myScreen.attrib.get("size"))
	screen.additionalWidgets = []
	screen.renderer = []
	usedComponents = set()

	def processNone(widget, context):
		pass

	def processWidget(widget, context):
		# Okay, we either have 1:1-mapped widgets ("old style"), or 1:n-mapped
		# widgets (source->renderer).
		wname = widget.attrib.get("name")
		wsource = widget.attrib.get("source")
		wconnection = widget.attrib.get("connection")
		wclass = widget.attrib.get("addon")
		source = None
		if wname is None and wsource is None and wclass is None:
			raise SkinError("The widget has no name, no source and no addon type specified")

		if wname:
			# print("[Skin] DEBUG: Widget name='%s'." % wname)
			usedComponents.add(wname)
			try:  # Get corresponding "gui" object.
				attributes = screen[wname].skinAttributes = []
			except Exception:
				raise SkinError("Component with name '%s' was not found in skin of screen '%s'" % (wname, name))
			# assert screen[wname] is not Source
			collectAttributes(attributes, widget, context, skinPath, ignore=("name",))
		elif wsource:
			# print("[Skin] DEBUG: Widget source='%s'." % wsource)
			while True:  # Get corresponding source until we found a non-obsolete source.
				# Parse our current "wsource", which might specify a "related screen" before the dot,
				# for example to reference a parent, global or session-global screen.
				scr = screen
				path = wsource.split(".")  # Resolve all path components.
				while len(path) > 1:
					scr = screen.getRelatedScreen(path[0])
					if scr is None:
						# print("[Skin] DEBUG: wsource='%s', name='%s'." % (wsource, name))
						raise SkinError("Specified related screen '%s' was not found in screen '%s'" % (wsource, name))
					path = path[1:]
				source = scr.get(path[0])  # Resolve the source.
				if isinstance(source, ObsoleteSource):
					# If we found an "obsolete source", issue warning, and resolve the real source.
					print("[Skin] WARNING: SKIN '%s' USES OBSOLETE SOURCE '%s', USE '%s' INSTEAD!" % (name, wsource, source.newSource))
					print("[Skin] OBSOLETE SOURCE WILL BE REMOVED %s, PLEASE UPDATE!" % source.removalDate)
					if source.description:
						print("[Skin] Source description: '%s'." % source.description)
					wsource = source.new_source
				else:
					break  # Otherwise, use the source.
			if source is None:
				raise SkinError("The source '%s' was not found in screen '%s'" % (wsource, name))

			wrender = widget.attrib.get("render")
			if not wrender:
				if wsource:
					raise SkinError("For source '%s' a renderer must be defined with a 'render=' attribute" % wsource)
				elif wconnection:
					raise SkinError("For connection '%s' a renderer must be defined with a 'render=' attribute" % wconnection)
			for converter in widget.findall("convert"):
				ctype = converter.get("type")
				nostrip = converter.get("nostrip") and converter.get("nostrip").lower() in ("1", "enabled", "nostrip", "on", "true", "yes")
				assert ctype, "[Skin] The 'convert' tag needs a 'type' attribute!"
				# print("[Skin] DEBUG: Converter='%s'." % ctype)
				try:
					parms = converter.text if nostrip else converter.text.strip()
				except Exception:
					parms = ""
				# print("[Skin] DEBUG: Params='%s'." % parms)
				try:
					converterClass = my_import(".".join(("Components", "Converter", ctype))).__dict__.get(ctype)
				except ImportError:
					raise SkinError("Converter '%s' not found" % ctype)
				c = None
				for i in source.downstream_elements:
					if isinstance(i, converterClass) and i.converter_arguments == parms:
						c = i
				if c is None:
					c = converterClass(parms)
					c.connect(source)
				source = c
			try:
				rendererClass = my_import(".".join(("Components", "Renderer", wrender))).__dict__.get(wrender)
			except ImportError:
				raise SkinError("Renderer '%s' not found" % wrender)
			renderer = rendererClass()  # Instantiate renderer.
			if source:
				renderer.connect(source)  # Connect to source.
				renderer.label_name = wsource or wname #allows that it can be checked a label exists in the skin
			attributes = renderer.skinAttributes = []
			collectAttributes(attributes, widget, context, skinPath, ignore=("render", "source"))
			screen.renderer.append(renderer)
		elif wclass:
			try:
				addonClass = my_import(".".join(("Components", "Addons", wclass))).__dict__.get(wclass)
			except ImportError:
				raise SkinError("GUI Addon '%s' not found" % wclass)

			if not wconnection:
				raise SkinError("The widget is from addon type: %s , but no connection is specified." % wclass)

			i = 0
			wclassname_base = name + "_" + wclass + "_" + wconnection + "_"
			while wclassname_base + str(i) in usedComponents:
				i += 1
			wclassname = wclassname_base + str(i)

			usedComponents.add(wclassname)

			screen[wclassname] = addonClass() #init the addon
			screen[wclassname].connectRelatedElement(wconnection, screen) #connect it to related ellement
			attributes = screen[wclassname].skinAttributes = []
			collectAttributes(attributes, widget, context, skinPath, ignore=("addon",))

	def processApplet(widget, context):
		try:
			codeText = widget.text.strip()
			widgetType = widget.attrib.get("type")
			code = compile(codeText, "skin applet", "exec")
		except Exception as err:
			raise SkinError("Applet failed to compile: '%s'" % str(err))
		if widgetType == "onLayoutFinish":
			screen.onLayoutFinish.append(code)
		elif widgetType == "onContentChanged":
			screen.onContentChanged.append(code)
		else:
			raise SkinError("Applet type '%s' is unknown" % widgetType)

	def processLabel(widget, context):
		w = additionalWidget()
		w.widget = eLabel
		w.skinAttributes = []
		collectAttributes(w.skinAttributes, widget, context, skinPath, ignore=("name",))
		screen.additionalWidgets.append(w)

	def processPixmap(widget, context):
		w = additionalWidget()
		w.widget = ePixmap
		w.skinAttributes = []
		collectAttributes(w.skinAttributes, widget, context, skinPath, ignore=("name",))
		screen.additionalWidgets.append(w)

	def processScreen(widget, context):
		for w in widget:
			conditional = w.attrib.get("conditional")
			if conditional and not [i for i in conditional.split(",") if i in screen.keys()]:
				continue
			objecttypes = w.attrib.get("objectTypes", "").split(",")
			if len(objecttypes) > 1 and (objecttypes[0] not in screen.keys() or not [i for i in objecttypes[1:] if i == screen[objecttypes[0]].__class__.__name__]):
				continue
			p = processors.get(w.tag, processNone)
			try:
				p(w, context)
			except SkinError as err:
				print("[Skin] Error in screen '%s' widget '%s' %s!" % (name, w.tag, str(err)))

	def processPanel(widget, context):
		n = widget.attrib.get("name")
		if n:
			try:
				s = domScreens[n]
			except KeyError:
				print("[Skin] Error: Unable to find screen '%s' referred in screen '%s'!" % (n, name))
			else:
				processScreen(s[0], context)
		layout = widget.attrib.get("layout")
		cc = SkinContextStack if layout == "stack" else SkinContext
		try:
			c = cc(context, widget.attrib.get("position"), widget.attrib.get("size"), widget.attrib.get("font"))
		except Exception as err:
			raise SkinError("Failed to create skin context (position='%s', size='%s', font='%s') in context '%s': %s" % (widget.attrib.get("position"), widget.attrib.get("size"), widget.attrib.get("font"), context, err))
		processScreen(widget, c)

	processors = {
		None: processNone,
		"widget": processWidget,
		"applet": processApplet,
		"eLabel": processLabel,
		"ePixmap": processPixmap,
		"panel": processPanel
	}

	try:
		msg = " from list '%s'" % ", ".join(names) if len(names) > 1 else ""
		posX = "?" if context.x is None else str(context.x)
		posY = "?" if context.y is None else str(context.y)
		sizeW = "?" if context.w is None else str(context.w)
		sizeH = "?" if context.h is None else str(context.h)
		print("[Skin] Processing screen '%s'%s, position=(%s, %s), size=(%s x %s) for module '%s'." % (name, msg, posX, posY, sizeW, sizeH, screen.__class__.__name__))
		context.x = 0  # Reset offsets, all components are relative to screen coordinates.
		context.y = 0
		processScreen(myScreen, context)
	except Exception as err:
		print("[Skin] Error in screen '%s' %s!" % (name, str(err)))

	from Components.GUIComponent import GUIComponent
	unusedComponents = [x for x in set(screen.keys()) - usedComponents if isinstance(x, GUIComponent)]
	assert not unusedComponents, "[Skin] The following components in '%s' don't have a skin entry: %s" % (name, ", ".join(unusedComponents))
	# This may look pointless, but it unbinds "screen" from the nested scope. A better
	# solution is to avoid the nested scope above and use the context object to pass
	# things around.
	screen = None
	usedComponents = None


def findWidgets(name):
	"""
	Return a set of all the widgets found in a screen. Panels will be expanded
	recursively until all referenced widgets are captured. This code only performs
	a simple scan of the XML and no skin processing is performed.
	"""
	widgetSet = set()
	element, path = domScreens.get(name, (None, None))
	if element is not None:
		widgets = element.findall("widget")
		if widgets is not None:
			for widget in widgets:
				name = widget.get("name", None)
				if name is not None:
					widgetSet.add(name)
				source = widget.get("source", None)
				if source is not None:
					widgetSet.add(source)
				addonConnection = widget.get("connection", None)
				if addonConnection is not None:
					for x in addonConnection.split(","):
						widgetSet.add(x)
		panels = element.findall("panel")
		if panels is not None:
			for panel in panels:
				name = panel.get("name", None)
				if name:
					widgetSet.update(findWidgets(name))
	return widgetSet


def getSkinFactor():
	"""
	Return a scaling factor (float) that can be used to rescale screen displays
	to suit the current resolution of the screen.  The scales are based on a
	default screen resolution of HD (720p).  That is the scale factor for a HD
	screen will be 1.
	"""
	skinfactor = getDesktop(GUI_SKIN_ID).size().height() / 720.0
	# if skinfactor not in [0.8, 1, 1.5, 3, 6]:
	# 	print("[Skin] Warning: Unexpected result for getSkinFactor '%0.4f'!" % skinfactor)
	return skinfactor


def applySkinFactor(*d):
	"""
	Multiply the numeric input by the skin factor
	and return the result as an integer.
	"""
	if len(d) == 1:
		return int(d[0] * getSkinFactor())
	return tuple([int(value * getSkinFactor()) if isinstance(value, (int, float)) else value for value in d])


def findSkinScreen(names):
	"""
	Search the domScreens dictionary to see if any of the screen names provided
	have a skin based screen.  This will allow coders to know if the named
	screen will be skinned by the skin code.  A return of None implies that the
	code must provide its own skin for the screen to be displayed to the user.
	"""
	if not isinstance(names, list):
		names = [names]
	for name in names:  # Try all names given, the first one found is the one that will be used by the skin engine.
		screen, path = domScreens.get(name, (None, None))
		if screen is not None:
			return name
	return None


def dump(x, i=0):
	print(" " * i + str(x))
	try:
		for n in x.childNodes:
			dump(n, i + 1)
	except Exception:
		None
