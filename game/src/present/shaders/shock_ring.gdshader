shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, shadows_disabled;
// Expanding ring/flash used for blocks, parries, guard breaks, barks and landings.

uniform vec4 color : source_color = vec4(1.0);
uniform float life = 0.0;        // 0..1
uniform float thickness = 0.12;
uniform int kind = 0;            // 0 ring, 1 filled flash

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float a = 0.0;
	if (kind == 0) {
		float rr = mix(0.15, 0.95, life);
		a = smoothstep(rr - thickness, rr, r) * (1.0 - smoothstep(rr, rr + thickness * 0.5, r));
	} else {
		a = 1.0 - smoothstep(0.0, 1.0, r);
		a *= a;
	}
	ALBEDO = color.rgb;
	ALPHA = a * (1.0 - life) * color.a;
}
