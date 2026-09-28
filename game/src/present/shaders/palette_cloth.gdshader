shader_type spatial;
// Palette-driven clothing (docs/CHARACTER_CONTRACT.md §4): mask R = primary, G = secondary,
// B = accent, none = trim. Detail texture carries fabric detail + baked AO (greyscale).

uniform sampler2D mask_tex : source_color, filter_linear_mipmap;
uniform sampler2D detail_tex : source_color, filter_linear_mipmap;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap;
uniform bool has_normal = false;
uniform vec4 primary : source_color = vec4(0.17, 0.18, 0.19, 1.0);
uniform vec4 secondary : source_color = vec4(0.6, 0.11, 0.13, 1.0);
uniform vec4 accent : source_color = vec4(0.78, 0.2, 0.23, 1.0);
uniform vec4 trim : source_color = vec4(0.11, 0.11, 0.12, 1.0);
uniform float roughness_base = 0.78;

void fragment() {
	vec3 m = texture(mask_tex, UV).rgb;
	float d = texture(detail_tex, UV).r;
	float trim_w = clamp(1.0 - (m.r + m.g + m.b), 0.0, 1.0);
	vec3 c = primary.rgb * m.r + secondary.rgb * m.g + accent.rgb * m.b + trim.rgb * trim_w;
	ALBEDO = c * (0.35 + 0.65 * d);
	ROUGHNESS = roughness_base - 0.12 * m.b;
	if (has_normal) {
		NORMAL_MAP = texture(normal_tex, UV).rgb;
	}
}
