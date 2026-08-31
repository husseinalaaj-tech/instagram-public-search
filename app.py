import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Animated Rings",
    page_icon="🌈",
    layout="wide",
)

st.title("🌈 High FPS Animated Rings")

fps = st.slider(
    "FPS",
    min_value=30,
    max_value=144,
    value=120,
    step=10,
)

ring_count = st.slider(
    "Number of Rings",
    min_value=3,
    max_value=40,
    value=15,
)

speed = st.slider(
    "Animation Speed",
    min_value=0.1,
    max_value=5.0,
    value=1.5,
    step=0.1,
)

components.html(
    f"""
<!DOCTYPE html>
<html>
<head>
<style>
html, body {{
    margin: 0;
    padding: 0;
    overflow: hidden;
    background: #050505;
}}

canvas {{
    display: block;
    width: 100%;
    height: 100%;
}}
</style>
</head>

<body>

<canvas id="canvas"></canvas>

<script>
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

let width = 0;
let height = 0;
let dpr = Math.min(window.devicePixelRatio || 1, 2);

function resize() {{
    width = window.innerWidth;
    height = window.innerHeight;

    canvas.width = width * dpr;
    canvas.height = height * dpr;

    canvas.style.width = width + "px";
    canvas.style.height = height + "px";

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}}

window.addEventListener("resize", resize);
resize();

const count = {ring_count};
const speed = {speed};

const rings = [];

for (let i = 0; i < count; i++) {{
    rings.push({{
        radius: 20 + i * 18,
        phase: Math.random() * Math.PI * 2,
        hue: (i / count) * 360,
        offset: Math.random() * 1000
    }});
}}

let last = performance.now();

function animate(now) {{

    const delta = Math.min(
        (now - last) / 1000,
        0.05
    );

    last = now;

    ctx.fillStyle = "rgba(5, 5, 5, 0.22)";
    ctx.fillRect(0, 0, width, height);

    const cx = width / 2;
    const cy = height / 2;

    for (let i = 0; i < rings.length; i++) {{

        const r = rings[i];

        r.phase += delta * speed;

        const x =
            cx +
            Math.cos(r.phase * 0.7 + i) *
            Math.min(width, height) *
            0.16;

        const y =
            cy +
            Math.sin(r.phase * 0.9 + i) *
            Math.min(width, height) *
            0.16;

        const radius =
            r.radius +
            Math.sin(r.phase * 2) * 12;

        const hue =
            (r.hue + now * 0.03) % 360;

        ctx.beginPath();

        ctx.arc(
            x,
            y,
            radius,
            0,
            Math.PI * 2
        );

        ctx.strokeStyle =
            `hsl(${{hue}}, 100%, 60%)`;

        ctx.lineWidth = 3;

        ctx.shadowBlur = 18;
        ctx.shadowColor =
            `hsl(${{hue}}, 100%, 55%)`;

        ctx.stroke();

        ctx.shadowBlur = 0;
    }}

    requestAnimationFrame(animate);
}}

requestAnimationFrame(animate);
</script>

</body>
</html>
""",
    height=700,
    scrolling=False,
)