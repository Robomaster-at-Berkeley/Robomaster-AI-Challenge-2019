"""
Describes all objects present in the challenge field
"""

import numpy as np
import math
import heapq
import cv2
import rendering

from utils import *
from strategy import *

"""
Every object is an implementation of the abstract class Character
"""
class Character:

	color = (0, 0, 0)

	def act(self, env):
		pass

	def render(self):
		pass

	def reset(self):
		pass

	def isRobot(self):
		return False

"""
All rectangular objects are described by class Rectangle

defined by the rectangle's center, width(x-span), height(y-span) and angle in degrees
"""
class Rectangle(Character):

	def __init__(self, bottom_left, width, height, angle=0):
		self.bottom_left = bottom_left
		self.width = width
		self.height = height
		self.setAngle(angle)
		self.angle_radian = angle / 180 * math.pi
		self.vertices = self.getVertices()
		self.center = self.getCenter()

	def getVertices(self):
		width_dx = math.cos(self.angle_radian) * self.width
		width_dy = math.sin(self.angle_radian) * self.width

		height_dx = -math.sin(self.angle_radian) * self.height
		height_dy = math.cos(self.angle_radian) * self.height

		bottom_right = self.bottom_left.move(width_dx, width_dy)
		top_left = self.bottom_left.move(height_dx, height_dy)
		top_right = bottom_right.move(height_dx, height_dy)

		return [self.bottom_left, bottom_right, top_right, top_left]

	def getCenter(self):
		return self.bottom_left.midpoint(self.vertices[2])

	def setAngle(self, deg):
		if deg < 0:
			return self.setAngle(deg + 360)
		if deg >= 360:
			return self.setAngle(deg - 360)
		self.angle = deg
		self.angle_radian = deg / 180 * math.pi

	"""
	Check if a point is contained by self. Uses some messy linalg. Please Suggest
	better implementation if possible.
	"""
	def contains(self, point):
		error_threshold = 0.01

		goal_vec = point.diff(self.bottom_left)

		width_vec = self.vertices[1].diff(self.bottom_left)
		height_vec = self.vertices[3].diff(self.bottom_left)

		width_proj = goal_vec.project(width_vec)
		height_proj = goal_vec.project(height_vec)

		return width_proj.length - self.width < error_threshold and \
		       height_proj.length - self.height < error_threshold and \
		       width_proj.dot(width_vec) >= 0 and \
			   height_proj.dot(height_vec) >= 0

	"""
	Checks if two rectangles intersect
	IT DOESN'T CONSIDER SOME CASES which I don't think are necessary for our app
	"""
	def intersects(self, other):
		return any([self.contains(v) for v in other.vertices] + \
		    [other.contains(v) for v in self.vertices])

	def blocks(self, point, vec):
		return self.contains(point)

	def angleTo(self, other):
		my_center, their_center = self.center, other.center
		return toDegree(their_center.diff(my_center).angle_radian())

	"Renders the rectangle depending on type"
	def render(self, color=None):
		rec = rendering.FilledPolygon([p.toList() for p in self.vertices])
		if not color:
			color = self.color
		rec.set_color(color[0], color[1], color[2])
		return rec


"""
Type of rectangle that never rotates.
Has implementation of certain methods that are more efficient
"""
class uprightRectangle(Rectangle):

	def getVertices(self):
		bottom_left = self.bottom_left
		bottom_right = bottom_left.move(self.width, 0)
		top_right = bottom_right.move(0, self.height)
		top_left = bottom_left.move(0, self.height)
		return [bottom_left, bottom_right, top_right, top_left]

	def contains(self, point):
		bottom_left, top_right = self.bottom_left, self.vertices[2]
		x, y = point.x, point.y
		return bottom_left.x <= x and bottom_left.y <= y and \
		    top_right.x >= x and top_right.y >= y

"""
Impermissible and inpenetrable obstacles are described by class Obstacle
"""
class Obstacle(uprightRectangle):

	def permissible(self, team):
		return False

	def penetrable(self):
		return False


"""
Permissble and penetrable areas in the field are described by class Zone
"""
class Zone(uprightRectangle):

	def __init__(self, bottom_left, width, height, team):
		super().__init__(bottom_left, width, height)
		self.team = team

	def penetrable(self):
		return True

	def permissble(self, team):
		return True


"""
Loading zones that provide 17mm bullets
"""
class LoadingZone(Zone):

	# color =

	life = 3

	"""
	Enemy loading zone is modeled as impermissible
	"""
	def permissble(self, team):
		return self.team == team

	"""
	Checks if the robot is aligned with the bullet supply machiary
	"""
	def aligned(self, robot):
		# Suggested implementation:
		# Model robot's buleet receiver as a Rectangle object
		# And use Rectangle.contains
		return True

	def load(self, robot):
		if self.life <= 0:
			return
		if self.aligned(robot):
			robot.load(100)
		self.life -= 1

	def life(self):
		return self.life

	def reset(self):
		self.life = 3


"""
Buff zone that boosts defense for one team
"""
class DefenseBuffZone(Zone):

	# color =

	active = True

	def activate(self):
		if self.active:
			self.team.addDefenseBuff(30)
			self.active = False

	def reset(self):
		self.active = True


class StartingZone(Zone):

	def __init__(self, env, team):
		sidelength = env.start_zone_sidelength
		if team.name == "BLUE":
			Rectangle.__init__(self, Point(0, 0), sidelength, sidelength)
			self.color = (0, 0, 0.5)
		elif team.name == "RED":
			point = Point(env.width - sidelength, env.height - sidelength)
			Rectangle.__init__(self, point, sidelength, sidelength)
			self.color = (0.5, 0, 0)


"""
Describes a bullet. Currently modeled as having constant speed and no volume
"""
class Bullet:

	damage = 20
	range = float('inf')

	def __init__(self, point, dir, team, env):
		self.delay = 0  # Models the delay from firing decision to bullet actually flying
		self.speed = 25
		self.travelled = 0
		self.point = point
		self.dir = dir / 180 * math.pi
		self.team = team
		self.env = env
		self.active = True

	def act(self):
		if not self.active:
			return
		if self.delay > 0:
			self.delay -= 1
			return
		move_point = self.point.move(math.cos(self.dir) * self.speed, math.sin(self.dir) * self.speed)
		move_vec = move_point.diff(self.point)
		for block in self.env.unpenetrables():
			if block.blocks(move_point, move_vec):
				self.destruct()
				if block.isRobot():
					block.reduceHealth(self.damage)
				return

		if self.env.isLegal(move_point):
			self.point = move_point
		else:
			self.destruct()

	"""
	SUBJECT TO CHANGE!
	"""
	def destruct(self):
		self.env.characters['bullets'] = list(filter(lambda b: not b == self, self.env.characters['bullets']))
		self.active = False

	def render(self):
		return Rectangle.render(Rectangle(self.point.move(-2.5, -2.5), 5, 5, 0), (0, 1, 0))

"""
The robot object -
Currently modeled as a Rectangle object by assumption that gun has negligible chance of blocking a bullet

To modify strategy, extend the class and override the `getStrategy` method
"""
class Robot(Rectangle):

	width = 50.0
	height = 30.0
	gun_width = height / 4
	gun_length = width
	range = float('inf') # More on this later

	max_forward_speed = 150
	max_sideway_speed = 100
	max_rotation_speed = 2

	def __init__(self, env, team, bottom_left, angle=0):
		self.health = 100
		self.gun_angle = 0
		self.env = env

		self.team = team
		self.color = team.color
		team.addRobot(self)
		self.defenseBuffTimer = 0
		super().__init__(bottom_left, Robot.width, Robot.height, angle)
		self.gun = self.getGun()
		self.gun_heat = 0
		self.bullet = 0

	def render(self):
		if self.alive():
			return [super().render(), Rectangle.render(self.gun, self.color)]
		return [super().render()]

	def alive(self):
		return self.health > 0

	def isRobot(self):
		return True

	def load(self, num):
		self.bullet += num

	def hasDefenseBuff(self):
		return self.defenseBuffTimer > 0

	def addDefenseBuff(self, time):
		self.defenseBuffTimer = time * 1000

	"""
	Determine a strategy based on information in self.env
	"""
	def getStrategy(self):
		pass

	"""
	The function evoked by Environment each turn
	First decide on an strategy, then execute it
	"""
	def act(self):
		if self.alive():
			self.defenseBuffTimer -= 1
			strategy = self.getStrategy()
			if strategy:
				action = strategy.decide(self, self)
				if action:
					if not type(action) == list:
						return self.execute(action)
					for action_part in action:
						self.execute(action_part)

	def execute(self, action):
		result_rec = action.resolve(self)
		if result_rec == None or self.env.isObstructed(result_rec, self):
			return
		self.setPosition(result_rec)

	def setPosition(self, rec):
		super().__init__(rec.bottom_left, rec.width, rec.height, rec.angle)
		self.gun = self.getGun()

	def getGun(self):
		bottom_left = self.vertices[1].midpoint(self.bottom_left).midpoint(self.center).midpoint(self.center)
		return Rectangle(bottom_left, self.gun_length, self.gun_width, self.angle)

	def reduceHealth(self, amount):
		if self.alive():
			if self.hasDefenseBuff():
				amount /= 2
			self.health = max(0, self.health - amount)


class DummyRobot(Robot):

	def getStrategy(self):
		return DoNothing


class CrazyRobot(Robot):

	def getStrategy(self):
		return SpinAndFire


class AttackRobot(Robot):

	def getStrategy(self):
		return AimAndFire

	# def set_speed(self, x_coord, y_coord):
	# 	x_speed = (x_coord - self.x)/10 * self.max_x_speed
	# 	y_speed = (y_coord - self.y)/10 * self.max_y_speed
	# 	return [min(x_speed, x_speed/abs(x_speed)*self.max_x_speed, key=lambda speed: abs(speed)), min(y_speed, y_speed/abs(y_speed)*self.max_y_speed, key=lambda speed: abs(speed))]
	#
	# def move(self, other_robot, env, x_coord, y_coord, obstacles, tau):
	# 	angle = self.angle * np.pi / 180
	#
	# 	x_speed, y_speed = self.set_speed(x_coord, y_coord)
	#
	# 	new_x = self.x + (x_speed*np.sin(angle) + y_speed*np.cos(angle))*tau
	# 	new_y = self.y + (-x_speed*np.cos(angle) + y_speed*np.sin(angle))*tau
	#
	# 	# Check for collisions
	#
	# 	# Outside Bounds
	# 	if new_x < self.width / 2:
	# 		new_x + self.width / 2
	# 	elif new_x + self.width / 2 > env.width:
	# 		new_x = env.width - self.width / 2
	#
	# 	if new_y < self.length / 2:
	# 		new_y = self.length / 2
	# 	elif new_y + self.length / 2 > env.height:
	# 		new_y = env.height - self.length / 2
	#
	# 	# Obstacles
	# 	for obstacle in obstacles:
	# 		l = obstacle.l - self.width / 2
	# 		r = obstacle.r + self.width / 2
	# 		b = obstacle.b - self.length / 2
	# 		t = obstacle.t + self.length / 2
	# 		if l < new_x < r and b < new_y < t:
	# 			if self.x <= l:
	# 				new_x = l
	# 			elif self.x >= r:
	# 				new_x = r
	# 			if self.y <= b:
	# 				new_y = b
	# 			elif self.y >= t:
	# 				new_y = t
	#
	# 	# Other robot
	# 	l = other_robot.x - other_robot.width / 2 - self.width / 2
	# 	r = other_robot.x + other_robot.width / 2 + self.width / 2
	# 	b = other_robot.y - other_robot.length / 2 - self.length / 2
	# 	t = other_robot.y + other_robot.length / 2 + self.length / 2
	#
	# 	if l < new_x < r and b < new_y < t:
	# 		if self.x <= l:
	# 			new_x = l
	# 		elif self.x >= r:
	# 			new_x = r
	# 		if self.y <= b:
	# 			new_y = b
	# 		elif self.y >= t:
	# 			new_y = t
	#
	# 	self.x, self.y = new_x, new_y
	#
	# def aim(self, other, obstacles):
	# 	if self.x == other.x:
	# 		if self.y > other.y:
	# 			gun_angle = -np.pi / 2
	# 		else:
	# 			gun_angle = np.pi / 2
	# 	elif self.x < other.x:
	# 		gun_angle = np.arctan((self.y - other.y) / (self.x - other.x))
	# 	else:
	# 		gun_angle = np.arctan((self.y - other.y) / (self.x - other.x)) + np.pi
	#
	# 	# Check for visual obstruction
	# 	x, y = self.x, self.y
	# 	step = 20
	#
	# 	obstructed = False
	# 	while abs(x - self.x) < abs(other.x - self.x):
	# 		for obstacle in obstacles:
	# 			if obstacle.surrounds(x, y):
	# 				obstructed = True # Return and skips the step of updating self.gun_angle
	# 		x += step * np.cos(gun_angle)
	# 		y += step * np.sin(gun_angle)
	#
	# 	if not obstructed:
	# 		self.gun_angle = (gun_angle * 180 / np.pi - 90) % 360
	#
	# def random_action(self):
	# 	return (np.random.random_sample(2,))*[800, 500]