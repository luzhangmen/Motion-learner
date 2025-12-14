#!/usr/bin/env python3
"""
3D人体重建 Demo - 手势控制测试版

使用方法:
    python demo_new.py
    python demo_new.py --port 8080

功能:
    - 自动加载 demo/demo1.jpg 进行3D重建
    - 支持摄像头手势控制3D模型
    - 无需文件上传，直接测试手势识别功能
"""

import argparse
import json
import os
import sys
import time
import threading
import webbrowser
import http.server
import socketserver
import socket
import ssl
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 全局状态
processing_status = {
    "is_processing": False,
    "progress": 0,
    "message": "",
    "error": None,
    "result_path": None,
    "is_video": False,
}

estimator = None
output_folder = Path("./output")
demo_image_path = Path("demo/demo1.jpg")

DEMO_HTML = '''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D人体重建 - 手势控制测试</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            overflow: hidden;
        }
        #container { width: 100vw; height: 100vh; }
        
        /* 加载面板 */
        #loading-panel {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.95);
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            min-width: 500px;
        }
        #loading-panel h2 { color: #4fc3f7; margin-bottom: 20px; }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #333;
            border-radius: 10px;
            overflow: hidden;
            margin: 20px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #4fc3f7, #81d4fa);
            width: 0%;
            transition: width 0.3s;
        }
        .progress-text {
            color: #aaa;
            font-size: 14px;
        }
        
        /* 信息面板 */
        #info {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            border-radius: 8px;
            font-size: 14px;
            max-width: 300px;
            display: none;
        }
        #info h3 { margin-bottom: 10px; color: #4fc3f7; }
        #info p { margin: 5px 0; color: #aaa; }
        
        /* 控制面板 */
        #controls {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            border-radius: 8px;
            display: none;
        }
        #controls button {
            display: block;
            width: 100%;
            padding: 8px 15px;
            margin: 5px 0;
            background: #4fc3f7;
            color: #000;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }
        #controls button:hover { background: #81d4fa; }
        #controls button.active { background: #0288d1; color: #fff; }
        .zoom-controls, .rotate-controls {
            display: flex;
            gap: 5px;
            margin-top: 5px;
        }
        .zoom-controls button, .rotate-controls button {
            flex: 1;
            padding: 6px !important;
        }
        
        /* 摄像头面板 */
        #camera-panel {
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.9);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
            border: 2px solid #66bb6a;
            display: none;
            max-width: 90%;
        }
        #camera-panel h3 { color: #66bb6a; margin-bottom: 15px; }
        #camera-panel p { color: #888; font-size: 12px; margin: 5px 0; }
        .camera-container {
            position: relative;
            display: inline-block;
            margin: 15px 0;
        }
        #camera-video {
            width: 320px;
            height: 240px;
            background: #000;
            border-radius: 8px;
        }
        #camera-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 320px;
            height: 240px;
            pointer-events: none;
        }
        .camera-controls {
            display: flex;
            gap: 10px;
            justify-content: center;
            margin-top: 15px;
        }
        .camera-controls button {
            padding: 8px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }
        #start-camera-btn {
            background: #66bb6a;
            color: #000;
        }
        #start-camera-btn:hover { background: #81c784; }
        #stop-camera-btn {
            background: #ef5350;
            color: #fff;
        }
        #stop-camera-btn:hover { background: #e57373; }
    </style>
</head>
<body>
    <div id="container"></div>
    
    <!-- 加载面板 -->
    <div id="loading-panel">
        <h2>3D人体重建 - 手势控制测试</h2>
        <p style="color: #888; margin-bottom: 20px;">正在加载示例图片并生成3D模型...</p>
        <div class="progress-bar">
            <div class="progress-fill" id="progress-fill"></div>
        </div>
        <div class="progress-text" id="progress-text">准备中...</div>
    </div>
    
    <!-- 信息面板 -->
    <div id="info">
        <h3>3D人体查看器</h3>
        <p>检测人数: <span id="num-people">-</span></p>
        <p>顶点数: <span id="num-vertices">-</span></p>
        <p>面片数: <span id="num-faces">-</span></p>
    </div>
    
    <!-- 控制面板 -->
    <div id="controls">
        <button id="btn-mesh" class="active">显示网格</button>
        <button id="btn-wireframe">显示线框</button>
        <button id="btn-skeleton">显示骨架</button>
        <hr style="border-color:#444;margin:10px 0;">
        <button id="btn-front">正面视角</button>
        <button id="btn-back">背面视角</button>
        <button id="btn-left">左侧视角</button>
        <button id="btn-right">右侧视角</button>
        <hr style="border-color:#444;margin:10px 0;">
        <div class="zoom-controls">
            <button id="btn-zoom-in" title="放大">+</button>
            <button id="btn-zoom-out" title="缩小">-</button>
        </div>
        <div class="rotate-controls">
            <button id="btn-rotate-ccw" title="逆时针">↺</button>
            <button id="btn-rotate-cw" title="顺时针">↻</button>
        </div>
        <hr style="border-color:#444;margin:10px 0;">
        <button id="btn-reset">重置视角</button>
        <button id="btn-lock" class="active">视角已锁定</button>
        <hr style="border-color:#444;margin:10px 0;">
        <button id="start-camera-btn">📷 开启摄像头</button>
    </div>
    
    <!-- 摄像头面板 -->
    <div id="camera-panel">
        <h3>手势控制模式</h3>
        <div class="camera-container">
            <video id="camera-video" autoplay playsinline></video>
            <canvas id="camera-canvas"></canvas>
        </div>
        <p><strong>手势说明:</strong></p>
        <p>👆 单指向上滑动 - 放大模型</p>
        <p>👇 单指向下滑动 - 缩小模型</p>
        <p>✋ 手掌张开旋转 - 旋转模型</p>
        <p>👊 握拳 - 重置视角</p>
        <p>✌️ 两指 - 切换显示模式</p>
        <div class="camera-controls">
            <button id="stop-camera-btn">关闭摄像头</button>
        </div>
    </div>

    <script type="importmap">
    {
        "imports": {
            "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
            "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
        }
    }
    </script>
    <!-- MediaPipe Hands -->
    <script src="https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1675469404/hands.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils@0.3.1640029074/camera_utils.js" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/@mediapipe/drawing_utils@0.3.1620248257/drawing_utils.js" crossorigin="anonymous"></script>

    <script type="module">
        import * as THREE from 'three';
        import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

        let scene, camera, renderer, controls;
        let meshes = [], skeletons = [];
        let showMesh = true, showWireframe = false, showSkeleton = false;
        let mhrData = null;
        let lockCamera = true, savedCameraState = null;
        let modelCenter = new THREE.Vector3();

        // 摄像头和手势识别相关
        let cameraStream = null;
        let hands = null;
        let camera = null;
        let isCameraMode = false;
        let gestureState = {
            lastHandPosition: null,
            lastGestureTime: 0,
            gestureCooldown: 500,
            zoomVelocity: 0,
            rotateVelocity: 0,
            lastFingerCount: 0
        };

        const SKELETON_CONNECTIONS = [
            [5,6],[5,7],[7,9],[6,8],[8,10],[11,12],[5,11],[6,12],
            [11,13],[13,15],[12,14],[14,16],[0,1],[0,2],[1,3],[2,4]
        ];
        const HAND_CONNECTIONS = [
            [0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],
            [0,9],[9,10],[10,11],[11,12],[0,13],[13,14],[14,15],[15,16],
            [0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]
        ];
        const HAND_CONNECTIONS_GESTURE = [
            [0, 1], [1, 2], [2, 3], [3, 4],
            [0, 5], [5, 6], [6, 7], [7, 8],
            [0, 9], [9, 10], [10, 11], [11, 12],
            [0, 13], [13, 14], [14, 15], [15, 16],
            [0, 17], [17, 18], [18, 19], [19, 20],
            [5, 9], [9, 13], [13, 17]
        ];

        // 初始化3D场景
        function initScene() {
            const container = document.getElementById('container');
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x1a1a2e);
            
            camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 1000);
            camera.position.set(0, 0, 3);
            
            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            container.appendChild(renderer.domElement);
            
            controls = new OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            
            scene.add(new THREE.AmbientLight(0xffffff, 0.5));
            const light1 = new THREE.DirectionalLight(0xffffff, 0.8);
            light1.position.set(5, 10, 7);
            scene.add(light1);
            const light2 = new THREE.DirectionalLight(0xffffff, 0.3);
            light2.position.set(-5, -5, -5);
            scene.add(light2);
            
            const grid = new THREE.GridHelper(10, 20, 0x444444, 0x333333);
            grid.position.y = -1;
            scene.add(grid);
            
            window.addEventListener('resize', () => {
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            });
            
            controls.addEventListener('end', () => {
                if (lockCamera) saveCameraState();
            });
            
            animate();
        }

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }

        // 加载3D模型
        async function loadModel() {
            try {
                const resp = await fetch('/api/mhr');
                if (!resp.ok) {
                    throw new Error('无法加载3D模型数据');
                }
                mhrData = await resp.json();
                updateInfo();
                createMeshes();
                
                document.getElementById('loading-panel').style.display = 'none';
                document.getElementById('info').style.display = 'block';
                document.getElementById('controls').style.display = 'block';
            } catch (e) {
                console.error('加载模型失败:', e);
                document.getElementById('progress-text').textContent = '加载失败: ' + e.message;
            }
        }

        function createMeshes() {
            meshes.forEach(m => scene.remove(m));
            skeletons.forEach(s => scene.remove(s));
            meshes = []; skeletons = [];
            
            if (!mhrData?.people) return;
            const faces = mhrData.faces;
            
            mhrData.people.forEach(person => {
                const vertices = person.mesh?.vertices;
                const keypoints = person.mesh?.keypoints_3d;
                
                if (vertices && faces) {
                    const geometry = new THREE.BufferGeometry();
                    const flipped = vertices.map(v => [v[0], -v[1], v[2]]).flat();
                    geometry.setAttribute('position', new THREE.Float32BufferAttribute(flipped, 3));
                    geometry.setIndex(faces.flat());
                    geometry.computeVertexNormals();
                    
                    const material = new THREE.MeshPhongMaterial({ color: 0x4fc3f7, side: THREE.DoubleSide });
                    const wireMat = new THREE.MeshBasicMaterial({ color: 0x4fc3f7, wireframe: true });
                    const mesh = new THREE.Mesh(geometry, material);
                    mesh.userData.wireframeMaterial = wireMat;
                    mesh.userData.solidMaterial = material;
                    scene.add(mesh);
                    meshes.push(mesh);
                }
                
                if (keypoints) {
                    const group = new THREE.Group();
                    const sphereGeo = new THREE.SphereGeometry(0.01, 8, 8);
                    const sphereMat = new THREE.MeshBasicMaterial({ color: 0xff5722 });
                    const flippedKps = keypoints.map(kp => [kp[0], -kp[1], kp[2]]);
                    
                    flippedKps.forEach(kp => {
                        const sphere = new THREE.Mesh(sphereGeo, sphereMat);
                        sphere.position.set(kp[0], kp[1], kp[2]);
                        group.add(sphere);
                    });
                    
                    const lineMat = new THREE.LineBasicMaterial({ color: 0xffeb3b });
                    const addBone = (i, j) => {
                        if (i < flippedKps.length && j < flippedKps.length) {
                            const pts = [new THREE.Vector3(...flippedKps[i]), new THREE.Vector3(...flippedKps[j])];
                            group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
                        }
                    };
                    SKELETON_CONNECTIONS.forEach(([i,j]) => addBone(i,j));
                    HAND_CONNECTIONS.forEach(([i,j]) => { addBone(21+i,21+j); addBone(42+i,42+j); });
                    
                    group.visible = showSkeleton;
                    scene.add(group);
                    skeletons.push(group);
                }
            });
            
            if (meshes.length > 0) {
                const box = new THREE.Box3();
                meshes.forEach(m => box.expandByObject(m));
                modelCenter = box.getCenter(new THREE.Vector3());
                
                if (lockCamera && savedCameraState) {
                    restoreCameraState();
                } else if (!savedCameraState) {
                    fitCameraToMeshes();
                    saveCameraState();
                }
            }
            applyViewSettings();
        }

        function updateInfo() {
            document.getElementById('num-people').textContent = mhrData?.num_people || 0;
            if (mhrData?.people?.length > 0) {
                const p = mhrData.people[0];
                document.getElementById('num-vertices').textContent = p.mesh?.vertices?.length || '-';
                document.getElementById('num-faces').textContent = mhrData.faces?.length || '-';
            }
        }

        function fitCameraToMeshes() {
            const box = new THREE.Box3();
            meshes.forEach(m => box.expandByObject(m));
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            camera.position.set(center.x, center.y, center.z + maxDim * 1.5);
            controls.target.copy(center);
            controls.update();
        }

        function saveCameraState() {
            savedCameraState = {
                position: camera.position.clone(),
                target: controls.target.clone()
            };
        }

        function restoreCameraState() {
            if (!savedCameraState) return;
            const offset = savedCameraState.position.clone().sub(savedCameraState.target);
            camera.position.copy(modelCenter).add(offset);
            controls.target.copy(modelCenter);
            controls.update();
        }

        function applyViewSettings() {
            meshes.forEach(mesh => {
                mesh.visible = showMesh || showWireframe;
                if (showWireframe && !showMesh) {
                    mesh.material = mesh.userData.wireframeMaterial;
                } else {
                    mesh.material = mesh.userData.solidMaterial;
                    mesh.material.wireframe = showWireframe;
                }
            });
            skeletons.forEach(s => s.visible = showSkeleton);
        }

        function toggleView(mode) {
            if (mode === 'mesh') { showMesh = !showMesh; document.getElementById('btn-mesh').classList.toggle('active', showMesh); }
            else if (mode === 'wireframe') { showWireframe = !showWireframe; document.getElementById('btn-wireframe').classList.toggle('active', showWireframe); }
            else if (mode === 'skeleton') { showSkeleton = !showSkeleton; document.getElementById('btn-skeleton').classList.toggle('active', showSkeleton); }
            applyViewSettings();
        }

        function setViewAngle(angle) {
            if (meshes.length === 0) return;
            const box = new THREE.Box3();
            meshes.forEach(m => box.expandByObject(m));
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const dist = Math.max(size.x, size.y, size.z) * 1.5;
            
            let pos;
            if (angle === 'front') pos = new THREE.Vector3(center.x, center.y, center.z + dist);
            else if (angle === 'back') pos = new THREE.Vector3(center.x, center.y, center.z - dist);
            else if (angle === 'left') pos = new THREE.Vector3(center.x - dist, center.y, center.z);
            else if (angle === 'right') pos = new THREE.Vector3(center.x + dist, center.y, center.z);
            
            camera.position.copy(pos);
            controls.target.copy(center);
            controls.update();
            if (lockCamera) saveCameraState();
        }

        function zoomCamera(factor) {
            const dir = new THREE.Vector3().subVectors(camera.position, controls.target).multiplyScalar(factor);
            camera.position.copy(controls.target).add(dir);
            controls.update();
            if (lockCamera) saveCameraState();
        }

        function rotateCamera(degrees) {
            const rad = degrees * Math.PI / 180;
            const offset = new THREE.Vector3().subVectors(camera.position, controls.target);
            const cos = Math.cos(rad), sin = Math.sin(rad);
            const newX = offset.x * cos - offset.z * sin;
            const newZ = offset.x * sin + offset.z * cos;
            offset.x = newX; offset.z = newZ;
            camera.position.copy(controls.target).add(offset);
            controls.update();
            if (lockCamera) saveCameraState();
        }

        // 摄像头相关功能
        document.getElementById('start-camera-btn').onclick = startCamera;
        document.getElementById('stop-camera-btn').onclick = stopCamera;
        
        async function startCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ 
                    video: { width: 320, height: 240 } 
                });
                cameraStream = stream;
                const video = document.getElementById('camera-video');
                video.srcObject = stream;
                
                document.getElementById('camera-panel').style.display = 'block';
                isCameraMode = true;
                
                await new Promise((resolve) => {
                    video.onloadedmetadata = () => {
                        video.play();
                        resolve();
                    };
                });
                
                // 初始化MediaPipe Hands
                let retries = 0;
                const initMediaPipe = () => {
                    if (typeof Hands !== 'undefined') {
                        if (!hands) {
                            try {
                                hands = new Hands({
                                    locateFile: (file) => {
                                        return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
                                    }
                                });
                                hands.setOptions({
                                    maxNumHands: 1,
                                    modelComplexity: 1,
                                    minDetectionConfidence: 0.5,
                                    minTrackingConfidence: 0.5
                                });
                                hands.onResults(onHandResults);
                                
                                if (typeof Camera !== 'undefined') {
                                    camera = new Camera(video, {
                                        onFrame: async () => {
                                            await hands.send({image: video});
                                        },
                                        width: 320,
                                        height: 240
                                    });
                                    camera.start();
                                } else {
                                    processCameraFrame();
                                }
                            } catch (error) {
                                console.error('MediaPipe初始化失败:', error);
                                processCameraFrameBasic();
                            }
                        }
                    } else if (retries < 10) {
                        retries++;
                        setTimeout(initMediaPipe, 100);
                    } else {
                        console.warn('MediaPipe Hands未加载');
                        processCameraFrameBasic();
                    }
                };
                initMediaPipe();
                
            } catch (error) {
                console.error('无法访问摄像头:', error);
                alert('无法访问摄像头，请检查权限设置');
            }
        }
        
        function processCameraFrame() {
            if (!isCameraMode || !cameraStream) return;
            const video = document.getElementById('camera-video');
            if (video.readyState === video.HAVE_ENOUGH_DATA && hands) {
                hands.send({image: video});
            }
            requestAnimationFrame(processCameraFrame);
        }
        
        function processCameraFrameBasic() {
            if (!isCameraMode || !cameraStream) return;
            const video = document.getElementById('camera-video');
            const canvas = document.getElementById('camera-canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = 320;
            canvas.height = 240;
            ctx.drawImage(video, 0, 0, 320, 240);
            requestAnimationFrame(processCameraFrameBasic);
        }
        
        function stopCamera() {
            if (camera) {
                camera.stop();
                camera = null;
            }
            if (cameraStream) {
                cameraStream.getTracks().forEach(track => track.stop());
                cameraStream = null;
            }
            document.getElementById('camera-panel').style.display = 'none';
            isCameraMode = false;
            gestureState = {
                lastHandPosition: null,
                lastGestureTime: 0,
                gestureCooldown: 500,
                zoomVelocity: 0,
                rotateVelocity: 0,
                lastFingerCount: 0
            };
        }
        
        function onHandResults(results) {
            const canvas = document.getElementById('camera-canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = 320;
            canvas.height = 240;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
                const landmarks = results.multiHandLandmarks[0];
                
                drawConnectors(ctx, landmarks, HAND_CONNECTIONS_GESTURE, {color: '#00FF00', lineWidth: 2});
                drawLandmarks(ctx, landmarks, {color: '#FF0000', lineWidth: 1, radius: 2});
                
                processGesture(landmarks);
            }
        }
        
        function processGesture(landmarks) {
            if (!meshes || meshes.length === 0) return;
            
            const now = Date.now();
            if (now - gestureState.lastGestureTime < gestureState.gestureCooldown) {
                return;
            }
            
            const fingerCount = countFingers(landmarks);
            const wrist = landmarks[0];
            const middleMCP = landmarks[9];
            const handCenter = {
                x: (wrist.x + middleMCP.x) / 2,
                y: (wrist.y + middleMCP.y) / 2
            };
            
            if (fingerCount === 1) {
                if (gestureState.lastHandPosition) {
                    const dy = handCenter.y - gestureState.lastHandPosition.y;
                    if (Math.abs(dy) > 0.02) {
                        if (dy < 0) {
                            zoomCamera(0.9);
                        } else {
                            zoomCamera(1.1);
                        }
                        gestureState.lastGestureTime = now;
                    }
                }
            }
            
            if (fingerCount === 5) {
                if (gestureState.lastHandPosition) {
                    const dx = handCenter.x - gestureState.lastHandPosition.x;
                    const distance = Math.sqrt(dx * dx + (handCenter.y - gestureState.lastHandPosition.y) * (handCenter.y - gestureState.lastHandPosition.y));
                    
                    if (distance > 0.03) {
                        const angle = dx * 30;
                        rotateCamera(angle);
                        gestureState.lastGestureTime = now;
                    }
                }
            }
            
            if (fingerCount === 0 && gestureState.lastFingerCount > 0) {
                fitCameraToMeshes();
                saveCameraState();
                gestureState.lastGestureTime = now;
            }
            
            if (fingerCount === 2 && gestureState.lastFingerCount !== 2) {
                if (showMesh && !showWireframe && !showSkeleton) {
                    showMesh = false;
                    showWireframe = true;
                    document.getElementById('btn-wireframe').classList.add('active');
                    document.getElementById('btn-mesh').classList.remove('active');
                } else if (showWireframe) {
                    showWireframe = false;
                    showSkeleton = true;
                    document.getElementById('btn-skeleton').classList.add('active');
                    document.getElementById('btn-wireframe').classList.remove('active');
                } else {
                    showSkeleton = false;
                    showMesh = true;
                    document.getElementById('btn-mesh').classList.add('active');
                    document.getElementById('btn-skeleton').classList.remove('active');
                }
                applyViewSettings();
                gestureState.lastGestureTime = now;
            }
            
            gestureState.lastHandPosition = handCenter;
            gestureState.lastFingerCount = fingerCount;
        }
        
        function countFingers(landmarks) {
            const fingerTips = [4, 8, 12, 16, 20];
            const fingerPIPs = [3, 6, 10, 14, 18];
            let count = 0;
            
            if (landmarks[4].x > landmarks[3].x) {
                count++;
            }
            
            for (let i = 1; i < 5; i++) {
                const tipIdx = fingerTips[i];
                const pipIdx = fingerPIPs[i];
                if (landmarks[tipIdx].y < landmarks[pipIdx].y) {
                    count++;
                }
            }
            
            return count;
        }
        
        function drawConnectors(ctx, points, connections, options) {
            ctx.strokeStyle = options.color || '#00FF00';
            ctx.lineWidth = options.lineWidth || 2;
            ctx.beginPath();
            for (const [start, end] of connections) {
                if (start < points.length && end < points.length) {
                    ctx.moveTo(points[start].x * 320, points[start].y * 240);
                    ctx.lineTo(points[end].x * 320, points[end].y * 240);
                }
            }
            ctx.stroke();
        }
        
        function drawLandmarks(ctx, points, options) {
            ctx.fillStyle = options.color || '#FF0000';
            for (const point of points) {
                ctx.beginPath();
                ctx.arc(point.x * 320, point.y * 240, options.radius || 2, 0, 2 * Math.PI);
                ctx.fill();
            }
        }

        // 事件绑定
        document.getElementById('btn-mesh').onclick = () => toggleView('mesh');
        document.getElementById('btn-wireframe').onclick = () => toggleView('wireframe');
        document.getElementById('btn-skeleton').onclick = () => toggleView('skeleton');
        document.getElementById('btn-front').onclick = () => setViewAngle('front');
        document.getElementById('btn-back').onclick = () => setViewAngle('back');
        document.getElementById('btn-left').onclick = () => setViewAngle('left');
        document.getElementById('btn-right').onclick = () => setViewAngle('right');
        document.getElementById('btn-reset').onclick = () => { fitCameraToMeshes(); saveCameraState(); };
        document.getElementById('btn-lock').onclick = () => {
            lockCamera = !lockCamera;
            const btn = document.getElementById('btn-lock');
            btn.classList.toggle('active', lockCamera);
            btn.textContent = lockCamera ? '视角已锁定' : '锁定视角';
            if (lockCamera) saveCameraState();
        };
        document.getElementById('btn-zoom-in').onclick = () => zoomCamera(0.8);
        document.getElementById('btn-zoom-out').onclick = () => zoomCamera(1.25);
        document.getElementById('btn-rotate-ccw').onclick = () => rotateCamera(-15);
        document.getElementById('btn-rotate-cw').onclick = () => rotateCamera(15);

        // 轮询进度
        async function pollProgress() {
            try {
                const response = await fetch('/api/progress');
                const status = await response.json();
                
                document.getElementById('progress-fill').style.width = status.progress + '%';
                document.getElementById('progress-text').textContent = status.message;
                
                if (status.error) {
                    alert('处理失败: ' + status.error);
                    return;
                }
                
                if (status.result_path) {
                    await loadModel();
                    return;
                }
                
                setTimeout(pollProgress, 500);
            } catch (e) {
                setTimeout(pollProgress, 1000);
            }
        }

        // 初始化
        initScene();
        
        // 页面加载后开始轮询进度
        window.addEventListener('load', () => {
            pollProgress();
        });
    </script>
</body>
</html>
'''

class DemoHandler(http.server.SimpleHTTPRequestHandler):
    """Demo HTTP请求处理器"""

    def send_cors_headers(self):
        """添加CORS头部"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        """处理预检请求"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(DEMO_HTML.encode('utf-8'))
            
        elif parsed.path == '/api/progress':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(processing_status).encode('utf-8'))
            
        elif parsed.path == '/api/mhr':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            if processing_status['result_path']:
                with open(processing_status['result_path'], 'r') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            else:
                self.wfile.write(b'{}')

        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        print(f"[HTTP] {self.command} {self.path} - {args[0] if args else ''}")


def process_file(filepath, frame_skip):
    """处理上传的文件"""
    global processing_status, estimator
    
    processing_status['is_processing'] = True
    processing_status['progress'] = 0
    processing_status['message'] = '正在加载模型...'
    processing_status['error'] = None
    processing_status['result_path'] = None
    
    try:
        import pyrootutils
        root = pyrootutils.setup_root(
            search_from=__file__,
            indicator=[".git", "pyproject.toml", ".sl"],
            pythonpath=True,
            dotenv=True,
        )
        
        import torch
        import cv2
        import numpy as np
        from sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
        from tools.mhr_io import save_mhr
        
        device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        
        # 加载模型(如果还没加载)
        if estimator is None:
            processing_status['message'] = '正在加载SAM 3D Body模型...'
            model, model_cfg = load_sam_3d_body(
                "./checkpoints/sam-3d-body-dinov3/model.ckpt",
                device=device,
                mhr_path="./checkpoints/sam-3d-body-dinov3/assets/mhr_model.pt"
            )
            
            processing_status['message'] = '正在加载人体检测器...'
            from tools.build_detector import HumanDetector
            human_detector = HumanDetector(name="vitdet", device=device, path="")
            
            processing_status['message'] = '正在加载FOV估计器...'
            from tools.build_fov_estimator import FOVEstimator
            fov_estimator = FOVEstimator(
                name="moge2", device=device, 
                path="./checkpoints/moge-2-vitl-normal/model.pt"
            )
            
            estimator = SAM3DBodyEstimator(
                sam_3d_body_model=model,
                model_cfg=model_cfg,
                human_detector=human_detector,
                human_segmentor=None,
                fov_estimator=fov_estimator,
            )
        
        processing_status['progress'] = 10
        
        # 处理图片
        processing_status['message'] = '正在处理图片...'
        processing_status['is_video'] = False
        
        img = cv2.imread(filepath)
        if img is None:
            raise ValueError("无法读取图片")
        
        image_size = (img.shape[1], img.shape[0])
        
        processing_status['progress'] = 30
        outputs = estimator.process_one_image(filepath, bbox_thr=0.8, use_mask=False)
        processing_status['progress'] = 80
        
        if not outputs:
            raise ValueError("未检测到人体")
        
        base_name = Path(filepath).stem
        mhr_path = output_folder / f"{base_name}.mhr.json"
        
        save_mhr(mhr_path, outputs, estimator.faces, image_path=filepath, image_size=image_size)
        
        processing_status['progress'] = 100
        processing_status['message'] = '处理完成!'
        processing_status['result_path'] = str(mhr_path)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        processing_status['error'] = str(e)
    finally:
        processing_status['is_processing'] = False


def find_free_port(start_port=8080):
    """查找可用端口"""
    for port in range(start_port, start_port + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    return start_port


def generate_self_signed_cert(cert_path, key_path):
    """生成自签名证书"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
        import ipaddress
        
        # 生成私钥
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # 获取本机IP
        import subprocess
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            local_ip = result.stdout.strip().split()[0] if result.stdout.strip() else '127.0.0.1'
        except:
            local_ip = '127.0.0.1'
        
        # 生成证书
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAM3D Demo"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        
        # 添加 SAN (Subject Alternative Name) 以支持 IP 访问
        san = x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("*.localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address(local_ip)),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            san, critical=False
        ).sign(key, hashes.SHA256(), default_backend())
        
        # 保存私钥
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # 保存证书
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        print(f"已生成自签名证书:")
        print(f"  证书: {cert_path}")
        print(f"  私钥: {key_path}")
        print(f"  包含 SAN: localhost, 127.0.0.1, {local_ip}")
        return True
        
    except ImportError:
        print("错误: 需要安装 cryptography 库来生成证书")
        print("请运行: pip install cryptography")
        print("或者手动生成证书:")
        print("  openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes")
        return False


def main():
    parser = argparse.ArgumentParser(description="3D人体重建 Demo - 手势控制测试版")
    parser.add_argument("--port", type=int, default=8080, help="服务器端口")
    parser.add_argument("--output", default="./output", help="输出目录")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--demo-image", default="demo/demo1.jpg", help="示例图片路径")
    parser.add_argument("--ssl", action="store_true", help="启用HTTPS (需要证书)")
    parser.add_argument("--cert", default="cert.pem", help="SSL证书文件路径 (默认: cert.pem)")
    parser.add_argument("--key", default="key.pem", help="SSL私钥文件路径 (默认: key.pem)")
    parser.add_argument("--auto-cert", action="store_true", help="自动生成自签名证书 (需要cryptography库)")
    args = parser.parse_args()

    global output_folder, demo_image_path
    output_folder = Path(args.output)
    output_folder.mkdir(parents=True, exist_ok=True)
    demo_image_path = Path(args.demo_image)

    if not demo_image_path.exists():
        print(f"错误: 示例图片不存在: {demo_image_path}")
        print(f"请确保文件存在，或使用 --demo-image 参数指定其他图片")
        sys.exit(1)

    # 处理SSL证书
    use_ssl = args.ssl or args.auto_cert
    if use_ssl:
        cert_path = Path(args.cert)
        key_path = Path(args.key)
        
        # 如果证书不存在且指定了自动生成
        if args.auto_cert and (not cert_path.exists() or not key_path.exists()):
            if not generate_self_signed_cert(str(cert_path), str(key_path)):
                print("无法生成证书，退出")
                sys.exit(1)
        
        # 检查证书文件是否存在
        if not cert_path.exists():
            print(f"错误: 证书文件不存在: {cert_path}")
            print("请使用 --auto-cert 自动生成，或手动创建证书:")
            print("  openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes")
            sys.exit(1)
        if not key_path.exists():
            print(f"错误: 私钥文件不存在: {key_path}")
            sys.exit(1)

    port = find_free_port(args.port)

    # 获取本机IP
    import subprocess
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        local_ip = result.stdout.strip().split()[0] if result.stdout.strip() else 'localhost'
    except:
        local_ip = 'localhost'

    # 使用多线程服务器
    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    protocol = "https" if use_ssl else "http"

    with ThreadedTCPServer((args.host, port), DemoHandler) as httpd:
        # 如果启用SSL，包装socket
        if use_ssl:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=args.cert, keyfile=args.key)
            httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        
        print(f"\n{'='*50}")
        print(f"3D人体重建 Demo - 手势控制测试版 已启动!")
        if use_ssl:
            print(f"\n[HTTPS模式] 摄像头功能可在远程使用")
            print(f"注意: 自签名证书需要在浏览器中手动信任")
        print(f"\n示例图片: {demo_image_path}")
        print(f"\n本地访问: {protocol}://localhost:{port}")
        print(f"远程访问: {protocol}://{local_ip}:{port}")
        print(f"\n正在自动处理示例图片，请稍候...")
        print(f"处理完成后，点击'开启摄像头'按钮测试手势控制功能")
        print(f"\n按 Ctrl+C 停止服务器")
        print(f"{'='*50}\n")

        # 在后台线程处理示例图片
        thread = threading.Thread(target=process_file, args=(str(demo_image_path), 0))
        thread.daemon = True
        thread.start()

        # 只在本地时自动打开浏览器
        if args.host in ('localhost', '127.0.0.1'):
            threading.Timer(1.0, lambda: webbrowser.open(f"{protocol}://localhost:{port}")).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")


if __name__ == "__main__":
    main()

