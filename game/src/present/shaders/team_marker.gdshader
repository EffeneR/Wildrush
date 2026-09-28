shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled;
// Ground marker under a fighter. Shape carries the relation, not only colour (spec §11):
// 0 = self (ring + forward chevron), 1 = ally (solid ring), 2 = enemy (four-notch ring).

uniform vec4 color : source_color = vec4(0.3, 0.6, 1.0, 1.0);
uniform int shape = 1;
uniform float alpha = 0.85;

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float ring = smoothstep(0.80, 0.84, r) * (1.0 - smoothstep(0.94, 0.98, r));
	float a = 0.0;
	if (shape == 2) {
		float ang = atan(p.y, p.x);
		float notch = step(0.82, abs(cos(ang * 2.0)));   // four heavy notches
		a = max(ring * (0.55 + 0.45 * notch), notch * smoothstep(0.66, 0.72, r) * (1.0 - smoothstep(0.98, 1.0, r)));
	} else {
		a = ring;
	}
	if (shape == 0) {
		// chevron toward -V (model forward is -Z; quad V runs along +Z)
		vec2 q = vec2(abs(p.x), -p.y);
		float chev = step(0.0, q.y - 0.58 + q.x * 0.9) * (1.0 - step(0.0, q.y - 0.78 + q.x * 0.9)) * step(q.x, 0.34);
		a = max(a, chev);
	}
	ALBEDO = color.rgb;
	ALPHA = a * alpha;
}
