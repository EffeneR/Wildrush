shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled;
// Territory ring on the ground. State is carried by pattern as well as colour (spec §11):
// 0 inactive (hidden), 1 next (dashed, pulsing), 2 neutral (solid), 3 controlled (solid +
// chevrons rotating), 4 contested (striped).

uniform vec4 color : source_color = vec4(0.98, 0.76, 0.22, 1.0);
uniform int state = 2;
uniform float radius = 9.0;
uniform float fill_alpha = 0.10;
uniform float progress = 0.0;       // not used for scoring; visual pulse only

void fragment() {
	vec2 p = (UV * 2.0 - 1.0) * (radius + 0.6);
	float r = length(p);
	float ang = atan(p.y, p.x);
	float edge = smoothstep(radius - 0.35, radius - 0.2, r) * (1.0 - smoothstep(radius + 0.05, radius + 0.2, r));
	float fill = (1.0 - smoothstep(radius - 0.25, radius - 0.1, r)) * fill_alpha;
	float t = TIME;
	float a = 0.0;
	if (state == 1) {
		float dash = step(0.0, sin(ang * 36.0));
		a = edge * dash * (0.55 + 0.35 * sin(t * 4.0));
		fill *= 0.4;
	} else if (state == 2) {
		a = edge;
	} else if (state == 3) {
		float chev = step(0.6, fract(ang / 6.2831853 * 18.0 + t * 0.35));
		a = max(edge, chev * smoothstep(radius - 1.0, radius - 0.8, r) * (1.0 - smoothstep(radius - 0.55, radius - 0.4, r)));
		fill *= 1.6;
	} else if (state == 4) {
		float stripe = step(0.5, fract((p.x + p.y) * 0.35 + t * 0.8));
		a = edge * (0.5 + 0.5 * stripe);
		fill *= (0.8 + 0.8 * stripe);
	}
	ALBEDO = color.rgb;
	ALPHA = clamp(a + fill, 0.0, 1.0) * (state == 0 ? 0.0 : 1.0);
}
