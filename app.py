import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Physics Sandbox",
    page_icon="🎮",
    layout="wide",
)

st.title("🎮 Physics Sandbox")
st.caption("لعبة Sandbox فيزيائية أصلية — نسخة تجريبية تعمل داخل المتصفح")

game = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<style>
    html, body {
        margin: 0;
        padding: 0;
        overflow: hidden;
        background: #111;
        touch-action: none;
        font-family: Arial, sans-serif;
    }

    canvas {
        display: block;
        background: #20242b;
    }

    #hud {
        position: fixed;
        top: 10px;
        left: 10px;
        color: white;
        background: rgba(0,0,0,.55);
        padding: 10px;
        border-radius: 10px;
        font-size: 14px;
        z-index: 5;
    }

    #buttons {
        position: fixed;
        bottom: 20px;
        left: 20px;
        right: 20px;
        display: flex;
        justify-content: space-between;
        pointer-events: none;
        z-index: 10;
    }

    .group {
        display: flex;
        gap: 10px;
    }

    button {
        width: 65px;
        height: 65px;
        border: 0;
        border-radius: 50%;
        background: rgba(255,255,255,.18);
        color: white;
        font-size: 25px;
        pointer-events: auto;
        user-select: none;
        -webkit-user-select: none;
    }

    button:active {
        background: rgba(255,255,255,.35);
    }

    #spawn {
        width: 130px;
        border-radius: 15px;
        font-size: 16px;
    }
</style>
</head>

<body>

<div id="hud">
    <b>PHYSICS SANDBOX</b><br>
    Objects: <span id="count">0</span><br>
    WASD / Arrows = Move<br>
    Space = Jump<br>
    Click/Tap = Spawn object
</div>

<div id="buttons">
    <div class="group">
        <button id="left">◀</button>
        <button id="right">▶</button>
    </div>

    <div class="group">
        <button id="spawn">SPAWN</button>
        <button id="jump">⬆</button>
    </div>
</div>

<canvas id="game"></canvas>

<script>
const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}
resize();
window.addEventListener("resize", resize);

const gravity = 0.65;
const groundHeight = 80;

const player = {
    x: 150,
    y: 200,
    w: 38,
    h: 58,
    vx: 0,
    vy: 0,
    speed: 0.7,
    maxSpeed: 6,
    jump: -12,
    grounded: false
};

const objects = [];

const keys = {
    left: false,
    right: false,
    jump: false
};

function spawnObject(x, y) {
    objects.push({
        x: x,
        y: y,
        w: 35 + Math.random() * 30,
        h: 35 + Math.random() * 30,
        vx: (Math.random() - .5) * 5,
        vy: -Math.random() * 5,
        rotation: Math.random() * Math.PI,
        vr: (Math.random() - .5) * .12
    });

    if (objects.length > 100) {
        objects.shift();
    }

    document.getElementById("count").textContent = objects.length;
}

function collide(a, b) {
    return (
        a.x < b.x + b.w &&
        a.x + a.w > b.x &&
        a.y < b.y + b.h &&
        a.y + a.h > b.y
    );
}

function updatePlayer() {
    if (keys.left) {
        player.vx -= player.speed;
    }

    if (keys.right) {
        player.vx += player.speed;
    }

    player.vx *= 0.86;

    if (player.vx > player.maxSpeed)
        player.vx = player.maxSpeed;

    if (player.vx < -player.maxSpeed)
        player.vx = -player.maxSpeed;

    if (keys.jump && player.grounded) {
        player.vy = player.jump;
        player.grounded = false;
    }

    player.vy += gravity;

    player.x += player.vx;
    player.y += player.vy;

    if (player.x < 0)
        player.x = 0;

    if (player.x + player.w > canvas.width)
        player.x = canvas.width - player.w;

    const groundY = canvas.height - groundHeight;

    if (player.y + player.h >= groundY) {
        player.y = groundY - player.h;
        player.vy = 0;
        player.grounded = true;
    }

    for (const obj of objects) {
        if (collide(player, obj)) {
            if (player.vy > 0 && player.y < obj.y) {
                player.y = obj.y - player.h;
                player.vy = 0;
                player.grounded = true;
            }
        }
    }
}

function updateObjects() {
    const groundY = canvas.height - groundHeight;

    for (const obj of objects) {

        obj.vy += gravity;

        obj.x += obj.vx;
        obj.y += obj.vy;

        obj.rotation += obj.vr;

        if (obj.x < 0) {
            obj.x = 0;
            obj.vx *= -0.7;
        }

        if (obj.x + obj.w > canvas.width) {
            obj.x = canvas.width - obj.w;
            obj.vx *= -0.7;
        }

        if (obj.y + obj.h > groundY) {
            obj.y = groundY - obj.h;
            obj.vy *= -0.55;
            obj.vx *= 0.92;

            if (Math.abs(obj.vy) < 0.5)
                obj.vy = 0;
        }
    }

    // Basic object-object physics
    for (let i = 0; i < objects.length; i++) {
        for (let j = i + 1; j < objects.length; j++) {

            const a = objects[i];
            const b = objects[j];

            if (collide(a, b)) {

                const centerA = a.x + a.w / 2;
                const centerB = b.x + b.w / 2;

                if (centerA < centerB) {
                    a.x -= 1;
                    b.x += 1;
                } else {
                    a.x += 1;
                    b.x -= 1;
                }

                const temp = a.vx;
                a.vx = b.vx * 0.8;
                b.vx = temp * 0.8;

                a.vy *= 0.8;
                b.vy *= 0.8;
            }
        }
    }
}

function drawBackground() {

    ctx.fillStyle = "#20242b";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Grid
    ctx.strokeStyle = "rgba(255,255,255,.05)";
    ctx.lineWidth = 1;

    for (let x = 0; x < canvas.width; x += 40) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
    }

    for (let y = 0; y < canvas.height; y += 40) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    }

    // Ground
    ctx.fillStyle = "#343b45";
    ctx.fillRect(
        0,
        canvas.height - groundHeight,
        canvas.width,
        groundHeight
    );
}

function drawPlayer() {

    ctx.save();

    ctx.translate(
        player.x + player.w / 2,
        player.y + player.h / 2
    );

    ctx.fillStyle = "#62a8ff";

    ctx.fillRect(
        -player.w / 2,
        -player.h / 2,
        player.w,
        player.h
    );

    ctx.fillStyle = "#fff";

    ctx.fillRect(-11, -15, 7, 7);
    ctx.fillRect(4, -15, 7, 7);

    ctx.restore();
}

function drawObjects() {

    for (const obj of objects) {

        ctx.save();

        ctx.translate(
            obj.x + obj.w / 2,
            obj.y + obj.h / 2
        );

        ctx.rotate(obj.rotation);

        ctx.fillStyle = "#d39b55";

        ctx.fillRect(
            -obj.w / 2,
            -obj.h / 2,
            obj.w,
            obj.h
        );

        ctx.strokeStyle = "#f1c27d";
        ctx.lineWidth = 3;

        ctx.strokeRect(
            -obj.w / 2,
            -obj.h / 2,
            obj.w,
            obj.h
        );

        ctx.restore();
    }
}

function render() {

    drawBackground();
    drawObjects();
    drawPlayer();

    requestAnimationFrame(render);
}

function loop() {
    updatePlayer();
    updateObjects();
    requestAnimationFrame(loop);
}

document.addEventListener("keydown", e => {

    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a")
        keys.left = true;

    if (e.key === "ArrowRight" || e.key.toLowerCase() === "d")
        keys.right = true;

    if (e.code === "Space")
        keys.jump = true;
});

document.addEventListener("keyup", e => {

    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a")
        keys.left = false;

    if (e.key === "ArrowRight" || e.key.toLowerCase() === "d")
        keys.right = false;

    if (e.code === "Space")
        keys.jump = false;
});

function holdButton(element, property) {

    element.addEventListener("touchstart", e => {
        e.preventDefault();
        keys[property] = true;
    });

    element.addEventListener("touchend", e => {
        e.preventDefault();
        keys[property] = false;
    });

    element.addEventListener("mousedown", () => {
        keys[property] = true;
    });

    element.addEventListener("mouseup", () => {
        keys[property] = false;
    });

    element.addEventListener("mouseleave", () => {
        keys[property] = false;
    });
}

holdButton(document.getElementById("left"), "left");
holdButton(document.getElementById("right"), "right");
holdButton(document.getElementById("jump"), "jump");

document.getElementById("spawn").addEventListener("click", () => {

    spawnObject(
        player.x + player.w + 20,
        player.y - 30
    );
});

canvas.addEventListener("pointerdown", e => {

    spawnObject(
        e.clientX,
        e.clientY
    );
});

for (let i = 0; i < 8; i++) {
    spawnObject(
        250 + i * 55,
        100
    );
}

render();
loop();
</script>

</body>
</html>
"""

components.html(game, height=700, scrolling=False)