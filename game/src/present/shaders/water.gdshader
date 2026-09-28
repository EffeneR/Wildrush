shader_type spatial;
render_mode cull_back, depth_draw_opaque;
// Harbour/canal water: layered moving normals, depth-tinted colour, soft specular.

uniform vec4 shallow : source_color = vec4(0.16, 0.34, 0.38, 1.0);
uniform vec4 deep : source_color = vec4(0.05, 0.14, 0.2, 1.0);
uniform float wave_scale = 0.18;
uniform float speed = 0.35;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

void fragment() {
	vec3 wp = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 uv = wp.xz * wave_scale;
	float t = TIME * speed;
	float n1 = noise(uv + vec2(t, t * 0.6));
	float n2 = noise(uv * 2.3 - vec2(t * 0.7, t * 1.1));
	float h = n1 * 0.6 + n2 * 0.4;
	float dx = noise(uv + vec2(0.05, 0.0) + vec2(t, t * 0.6)) - n1;
	float dz = noise(uv + vec2(0.0, 0.05) + vec2(t, t * 0.6)) - n1;
	NORMAL_MAP = normalize(vec3(-dx * 4.0 + 0.5, -dz * 4.0 + 0.5, 1.0));
	NORMAL_MAP_DEPTH = 0.6;
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALBEDO = mix(deep.rgb, shallow.rgb, 0.35 + 0.4 * h);
	ROUGHNESS = 0.06;
	METALLIC = 0.0;
	SPECULAR = 0.6;
	EMISSION = vec3(0.02, 0.04, 0.05) * fres;
}
