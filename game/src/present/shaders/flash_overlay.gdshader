shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, shadows_disabled;
// Additive overlay for hit confirms, guard flashes and spawn protection shimmer.

uniform vec4 color : source_color = vec4(1.0, 1.0, 1.0, 1.0);
uniform float amount = 0.0;
uniform float fresnel_power = 2.0;

void fragment() {
	float f = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), fresnel_power);
	ALBEDO = color.rgb;
	ALPHA = clamp(amount * (0.35 + 0.65 * f), 0.0, 1.0);
}
