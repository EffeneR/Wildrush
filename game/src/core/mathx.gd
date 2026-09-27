class_name MathX
extends RefCounted
## Deterministic geometry helpers used by the authoritative simulation.


static func yaw_forward(yaw: float) -> Vector3:
	## D-003: yaw 0 faces -Z (north). forward = -basis.z.
	return Vector3(-sin(yaw), 0.0, -cos(yaw))


static func yaw_right(yaw: float) -> Vector3:
	return Vector3(cos(yaw), 0.0, -sin(yaw))


static func yaw_from_dir(dir: Vector3) -> float:
	return atan2(-dir.x, -dir.z)


static func local_to_world(origin: Vector3, yaw: float, local: Vector3) -> Vector3:
	## Action-local (x right, y up, z forward) -> world.
	return origin + yaw_right(yaw) * local.x + Vector3.UP * local.y + yaw_forward(yaw) * local.z


static func world_dir_to_local(yaw: float, v: Vector3) -> Vector3:
	return Vector3(v.dot(yaw_right(yaw)), v.y, v.dot(yaw_forward(yaw)))


static func angle_diff(a: float, b: float) -> float:
	## Smallest signed difference b - a in (-PI, PI].
	return wrapf(b - a, -PI, PI)


static func rotate_toward(current: float, target: float, max_step: float) -> float:
	var d: float = angle_diff(current, target)
	if absf(d) <= max_step:
		return wrapf(target, -PI, PI)
	return wrapf(current + signf(d) * max_step, -PI, PI)


static func closest_points_segments(p1: Vector3, q1: Vector3, p2: Vector3, q2: Vector3) -> Array:
	## Returns [point_on_seg1, point_on_seg2]. Robust for degenerate segments.
	var d1: Vector3 = q1 - p1
	var d2: Vector3 = q2 - p2
	var r: Vector3 = p1 - p2
	var a: float = d1.dot(d1)
	var e: float = d2.dot(d2)
	var f: float = d2.dot(r)
	var s: float = 0.0
	var t: float = 0.0
	const EPS: float = 1e-9
	if a <= EPS and e <= EPS:
		return [p1, p2]
	if a <= EPS:
		s = 0.0
		t = clampf(f / e, 0.0, 1.0)
	else:
		var c: float = d1.dot(r)
		if e <= EPS:
			t = 0.0
			s = clampf(-c / a, 0.0, 1.0)
		else:
			var b: float = d1.dot(d2)
			var denom: float = a * e - b * b
			if denom > EPS:
				s = clampf((b * f - c * e) / denom, 0.0, 1.0)
			else:
				s = 0.0
			t = (b * s + f) / e
			if t < 0.0:
				t = 0.0
				s = clampf(-c / a, 0.0, 1.0)
			elif t > 1.0:
				t = 1.0
				s = clampf((b - c) / a, 0.0, 1.0)
	return [p1 + d1 * s, p2 + d2 * t]


static func segment_segment_distance(p1: Vector3, q1: Vector3, p2: Vector3, q2: Vector3) -> float:
	var cp: Array = closest_points_segments(p1, q1, p2, q2)
	return (cp[0] as Vector3).distance_to(cp[1] as Vector3)


static func point_segment_distance_2d(p: Vector2, a: Vector2, b: Vector2) -> float:
	var ab: Vector2 = b - a
	var l2: float = ab.length_squared()
	if l2 < 1e-9:
		return p.distance_to(a)
	var t: float = clampf((p - a).dot(ab) / l2, 0.0, 1.0)
	return p.distance_to(a + ab * t)


static func sample_keys(keys: Array, t: float) -> Vector3:
	## keys: Array of [time_s: float, Vector3]; linear interpolation, clamped.
	if keys.is_empty():
		return Vector3.ZERO
	if t <= float(keys[0][0]):
		return keys[0][1]
	for i in range(1, keys.size()):
		var t1: float = float(keys[i][0])
		if t <= t1:
			var t0: float = float(keys[i - 1][0])
			var u: float = 0.0 if t1 - t0 < 1e-9 else (t - t0) / (t1 - t0)
			return (keys[i - 1][1] as Vector3).lerp(keys[i][1] as Vector3, u)
	return keys[keys.size() - 1][1]


static func sample_keys_smooth(keys: Array, t: float) -> Vector3:
	## Same as sample_keys but with smoothstep easing inside each segment (movement curves).
	if keys.is_empty():
		return Vector3.ZERO
	if t <= float(keys[0][0]):
		return keys[0][1]
	for i in range(1, keys.size()):
		var t1: float = float(keys[i][0])
		if t <= t1:
			var t0: float = float(keys[i - 1][0])
			var u: float = 0.0 if t1 - t0 < 1e-9 else (t - t0) / (t1 - t0)
			u = u * u * (3.0 - 2.0 * u)
			return (keys[i - 1][1] as Vector3).lerp(keys[i][1] as Vector3, u)
	return keys[keys.size() - 1][1]


static func ease_out(u: float) -> float:
	u = clampf(u, 0.0, 1.0)
	return 1.0 - (1.0 - u) * (1.0 - u)


static func is_finite_vec3(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)
