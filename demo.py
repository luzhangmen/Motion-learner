#!/usr/bin/env python3
"""
3D人体重建 Demo - 一体化网页应用

使用方法:
    python demo.py
    python demo.py --port 8080

功能:
    - 直接运行打开网页
    - 上传图片/视频进行处理
    - 显示处理进度
    - 处理完成后直接在页面查看3D模型
"""

import argparse
import json
import os
import sys
import time
import tempfile
import threading
import webbrowser
import http.server
import socketserver
import socket
import shutil
import base64
import ssl
import ipaddress
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from io import BytesIO

# 全局状态
processing_status = {
    "is_processing": False,
    "progress": 0,
    "message": "",
    "current_frame": 0,
    "total_frames": 0,
    "eta": "",
    "error": None,
    "result_path": None,
    "is_video": False,
}

estimator = None
output_folder = Path("./output")

DEMO_HTML = '''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D人体重建 Demo</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            overflow: hidden;
        }
        #container { width: 100vw; height: 100vh; }
        
        /* 上传面板 */
        #upload-panel {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.9);
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            border: 2px dashed #4fc3f7;
            min-width: 400px;
        }
        #upload-panel.hidden { display: none; }
        #upload-panel h2 { color: #4fc3f7; margin-bottom: 20px; }
        #upload-panel p { color: #888; margin-bottom: 20px; }
        
        .upload-area {
            border: 2px dashed #555;
            border-radius: 12px;
            padding: 40px;
            margin: 20px 0;
            cursor: pointer;
            transition: all 0.3s;
            min-height: 200px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: #4fc3f7;
            background: rgba(79, 195, 247, 0.1);
            border-width: 3px;
        }
        .upload-area input { 
            display: none; 
            position: absolute;
            width: 0;
            height: 0;
            opacity: 0;
            pointer-events: none;
        }
        .upload-icon { font-size: 64px; margin-bottom: 15px; }
        
        .upload-btn {
            background: #4fc3f7;
            color: #000;
            border: none;
            padding: 12px 30px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            margin: 10px;
        }
        .upload-btn:hover { background: #81d4fa; }
        
        .options {
            margin-top: 20px;
            text-align: left;
            padding: 15px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }
        .options label {
            display: flex;
            align-items: center;
            margin: 8px 0;
            color: #aaa;
        }
        .options input[type="number"] {
            width: 60px;
            background: #333;
            border: 1px solid #555;
            color: #fff;
            padding: 4px 8px;
            border-radius: 4px;
            margin-left: 10px;
        }
        
        /* 进度面板 */
        #progress-panel {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.95);
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            min-width: 500px;
            display: none;
        }
        #progress-panel h3 { color: #4fc3f7; margin-bottom: 20px; }
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
        .progress-detail {
            margin-top: 15px;
            color: #666;
            font-size: 12px;
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
        
        /* 新建按钮 */
        #new-btn {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.7);
            padding: 8px 20px;
            border-radius: 8px;
            display: none;
        }
        #new-btn button {
            background: #4fc3f7;
            color: #000;
            border: none;
            padding: 8px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        #new-btn button:hover { background: #81d4fa; }
        
        /* 播放器控制 */
        #player-controls {
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 15px 25px;
            border-radius: 10px;
            display: none;
            align-items: center;
            gap: 15px;
        }
        #player-controls button {
            background: #4fc3f7;
            color: #000;
            border: none;
            border-radius: 4px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 16px;
        }
        #player-controls button:hover { background: #81d4fa; }
        #player-controls button.active { background: #0288d1; color: #fff; }
        #frame-slider { width: 300px; cursor: pointer; }
        #frame-info { color: #aaa; font-size: 14px; min-width: 100px; }
        #speed-control {
            display: flex;
            align-items: center;
            gap: 5px;
            color: #aaa;
            font-size: 12px;
        }
        #speed-display {
            min-width: 40px;
            text-align: center;
            color: #4fc3f7;
            font-weight: bold;
        }
        .player-separator {
            width: 1px;
            height: 20px;
            background: #555;
        }
        #jump-control {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        #jump-input {
            width: 50px;
            background: #333;
            border: 1px solid #555;
            color: #fff;
            padding: 4px;
            border-radius: 4px;
            text-align: center;
        }
        
        /* 标记面板 */
        #markers-panel {
            position: absolute;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.8);
            padding: 10px 15px;
            border-radius: 8px;
            display: none;
            max-width: 600px;
        }
        #markers-panel h4 { color: #4fc3f7; margin-bottom: 8px; font-size: 12px; }
        #markers-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            max-height: 100px;
            overflow-y: auto;
        }
        .marker-item {
            background: #333;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .marker-item:hover { background: #444; }
        .marker-item .delete-marker {
            color: #f44336;
            cursor: pointer;
        }
        
        /* 摄像头面板 */
        #camera-panel {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.9);
            padding: 40px;
            border-radius: 16px;
            text-align: center;
            border: 2px dashed #66bb6a;
            min-width: 700px;
        }
        #camera-panel.hidden { display: none; }
        #camera-panel h2 { color: #66bb6a; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div id="container"></div>
    
    <!-- 上传面板 -->
    <div id="upload-panel">
        <h2>3D人体重建 Demo</h2>
        <p>上传图片或视频，自动提取3D人体模型</p>
        
        <div class="upload-area" id="drop-area">
            <div class="upload-icon">📁</div>
            <p><strong>方式1: 拖拽文件到这里</strong></p>
            <p style="font-size:14px;color:#888;margin:10px 0;">或</p>
            <p><strong>方式2: 点击下方按钮选择文件</strong></p>
            <p style="font-size:12px;color:#666;margin-top:15px;">支持格式: JPG, PNG, BMP, WEBP, MP4, AVI, MOV, MKV, WEBM</p>
            <p style="font-size:11px;color:#555;margin-top:5px;">最大文件大小: 建议不超过500MB</p>
            <input type="file" id="file-input" accept="image/*,video/*" style="position: absolute; width: 100%; height: 100%; top: 0; left: 0; opacity: 0; cursor: pointer; z-index: 10;">
        </div>
        
        <div class="options">
            <label>
                <span>视频跳帧:</span>
                <input type="number" id="frame-skip" value="0" min="0" max="10">
                <span style="color:#666;margin-left:10px;">(0=不跳帧, 适用于视频处理)</span>
            </label>
        </div>
        
        <div style="display: flex; gap: 10px; justify-content: center; margin-top: 20px;">
            <button class="upload-btn" id="select-btn" style="flex: 1; max-width: 200px;">📤 选择文件上传</button>
            <button class="upload-btn" id="camera-btn" style="background: #66bb6a; flex: 1; max-width: 200px;">📷 开启摄像头</button>
        </div>
        
        <div style="margin-top: 20px; padding: 15px; background: rgba(79, 195, 247, 0.1); border-radius: 8px; border-left: 3px solid #4fc3f7;">
            <p style="font-size: 12px; color: #81d4fa; margin: 0;">
                <strong>💡 使用提示:</strong><br>
                • 上传图片: 支持单张图片的3D重建<br>
                • 上传视频: 支持逐帧处理，可设置跳帧以加快处理速度<br>
                • 摄像头模式: 实时捕获并处理，支持手势控制
            </p>
        </div>
    </div>
    
    <!-- 摄像头面板 -->
    <div id="camera-panel" class="hidden">
        <h2>摄像头模式</h2>
        <p>使用手势控制3D模型</p>
        <div style="position: relative; display: inline-block; margin: 20px 0;">
            <video id="camera-video" autoplay playsinline style="width: 640px; height: 480px; background: #000; border-radius: 8px;"></video>
            <canvas id="camera-canvas" style="position: absolute; top: 0; left: 0; width: 640px; height: 480px; pointer-events: none;"></canvas>
        </div>
        <div style="margin: 15px 0;">
            <p style="color: #888; font-size: 14px; margin: 10px 0;">
                <strong>手势说明:</strong><br>
                👆 单指向上滑动 - 放大模型<br>
                👇 单指向下滑动 - 缩小模型<br>
                ✋ 手掌张开旋转 - 旋转模型<br>
                👊 握拳 - 重置视角<br>
                ✌️ 两指 - 切换显示模式
            </p>
        </div>
        <button class="upload-btn" id="stop-camera-btn" style="background: #ef5350;">关闭摄像头</button>
        <button class="upload-btn" id="capture-btn" style="background: #ffa726;">捕获并处理</button>
    </div>
    
    <!-- 进度面板 -->
    <div id="progress-panel">
        <h3>正在处理...</h3>
        <div class="progress-bar">
            <div class="progress-fill" id="progress-fill"></div>
        </div>
        <div class="progress-text" id="progress-text">准备中...</div>
        <div class="progress-detail" id="progress-detail"></div>
    </div>
    
    <!-- 信息面板 -->
    <div id="info">
        <h3>3D人体查看器</h3>
        <p>检测人数: <span id="num-people">-</span></p>
        <p>顶点数: <span id="num-vertices">-</span></p>
        <p>面片数: <span id="num-faces">-</span></p>
        <p id="video-info-text" style="display:none;">视频帧: <span id="current-frame">-</span></p>
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
    </div>
    
    <!-- 新建按钮 -->
    <div id="new-btn">
        <button id="btn-new">上传新文件</button>
    </div>
    
    <!-- 标记面板 -->
    <div id="markers-panel">
        <h4>进度标记 (M键添加)</h4>
        <div id="markers-list"></div>
    </div>
    
    <!-- 播放器控制 -->
    <div id="player-controls">
        <button id="btn-fast-backward" title="快退5帧">⏪</button>
        <button id="btn-prev" title="上一帧">⏮</button>
        <button id="btn-play" title="播放/暂停">▶</button>
        <button id="btn-next" title="下一帧">⏭</button>
        <button id="btn-fast-forward" title="快进5帧">⏩</button>
        <div class="player-separator"></div>
        <input type="range" id="frame-slider" min="0" max="100" value="0">
        <span id="frame-info">0 / 0</span>
        <div class="player-separator"></div>
        <div id="speed-control">
            <button id="btn-speed-down">-</button>
            <span id="speed-display">1.0x</span>
            <button id="btn-speed-up">+</button>
        </div>
        <div class="player-separator"></div>
        <div id="jump-control">
            <input type="number" id="jump-input" placeholder="帧" min="1">
            <button id="jump-btn">跳转</button>
        </div>
        <div class="player-separator"></div>
        <button id="btn-marker" title="标记">🔖</button>
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
        let mhrData = null, sharedFaces = null;
        let lockCamera = true, savedCameraState = null;
        let modelCenter = new THREE.Vector3();

        // 视频相关
        let isVideoMode = false, videoInfo = null, frameFiles = [];
        let currentFrameIndex = 0, isPlaying = false, playFPS = 10;
        let frameCache = {}, playbackSpeed = 1.0, frameMarkers = [];
        let isLoadingFrame = false;
        const FAST_SKIP_FRAMES = 5;
        
        // 摄像头和手势识别相关
        let cameraStream = null;
        let hands = null;
        let camera = null;
        let isCameraMode = false;
        let gestureState = {
            lastHandPosition: null,
            lastGestureTime: 0,
            gestureCooldown: 500, // 手势冷却时间(ms)
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

        // 文件上传 - 确保DOM加载完成后再初始化
        function initUploadHandlers() {
        const dropArea = document.getElementById('drop-area');
        const fileInput = document.getElementById('file-input');
        const selectBtn = document.getElementById('select-btn');

            if (!dropArea || !fileInput || !selectBtn) {
                console.error('上传组件元素未找到，重试中...');
                setTimeout(initUploadHandlers, 100);
                return;
            }

            console.log('初始化上传组件...', { dropArea, fileInput, selectBtn });

            // 清除之前的事件监听器（如果有）
            const newSelectBtn = selectBtn.cloneNode(true);
            selectBtn.parentNode.replaceChild(newSelectBtn, selectBtn);
            
            const newFileInput = fileInput.cloneNode(true);
            fileInput.parentNode.replaceChild(newFileInput, fileInput);

            // 重新获取元素引用
            const actualSelectBtn = document.getElementById('select-btn');
            const actualFileInput = document.getElementById('file-input');
            const actualDropArea = document.getElementById('drop-area');

            // 绑定选择按钮事件
            actualSelectBtn.addEventListener('click', (e) => {
                e.preventDefault();
            e.stopPropagation();
            console.log('点击选择按钮');
                try {
                    // 确保文件输入框可见且可点击
                    actualFileInput.style.display = 'block';
                    actualFileInput.style.position = 'fixed';
                    actualFileInput.style.top = '50%';
                    actualFileInput.style.left = '50%';
                    actualFileInput.style.transform = 'translate(-50%, -50%)';
                    actualFileInput.style.zIndex = '9999';
                    actualFileInput.style.opacity = '0.01';
                    actualFileInput.style.width = '1px';
                    actualFileInput.style.height = '1px';
                    
                    actualFileInput.click();
                    console.log('文件选择对话框已触发');

                    // 延迟后恢复样式
                    setTimeout(() => {
                        actualFileInput.style.cssText = 'position: absolute; width: 100%; height: 100%; top: 0; left: 0; opacity: 0; cursor: pointer; z-index: 10;';
                    }, 100);
                } catch (error) {
                    console.error('触发文件选择失败:', error);
                    alert('无法打开文件选择对话框。请尝试:\n1. 检查浏览器权限设置\n2. 尝试直接点击上传区域\n3. 使用拖拽方式上传\n\n错误: ' + error.message);
                }
            });

            // 绑定上传区域点击事件（直接点击区域也可以选择文件）
            actualDropArea.addEventListener('click', (e) => {
                // 如果点击的是按钮，不处理（按钮有自己的事件）
                if (e.target === actualSelectBtn || e.target.closest('#select-btn') || e.target.closest('#camera-btn')) {
                    return;
                }
                // 如果点击的是文件输入框，不处理
                if (e.target === actualFileInput) {
                    return;
                }
                
                console.log('点击上传区域');
                try {
                    actualFileInput.click();
                    console.log('文件选择对话框已触发（通过区域点击）');
                } catch (error) {
                    console.error('触发文件选择失败:', error);
            }
            });

        ['dragenter','dragover'].forEach(e => {
            dropArea.addEventListener(e, (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                dropArea.classList.add('dragover');
            });
        });
        ['dragleave','drop'].forEach(e => {
            dropArea.addEventListener(e, (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                dropArea.classList.remove('dragover');
            });
        });

            // 绑定拖拽事件
            ['dragenter','dragover'].forEach(e => {
                actualDropArea.addEventListener(e, (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    actualDropArea.classList.add('dragover');
                });
            });
            ['dragleave','drop'].forEach(e => {
                actualDropArea.addEventListener(e, (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    actualDropArea.classList.remove('dragover');
                });
            });

            actualDropArea.addEventListener('drop', (e) => {
            console.log('文件拖放');
            const file = e.dataTransfer.files[0];
            if (file) {
                console.log('拖放文件:', file.name);
                handleFile(file);
            }
        });

            // 绑定文件选择变化事件
            actualFileInput.addEventListener('change', (e) => {
            console.log('文件选择变化');
                if (actualFileInput.files && actualFileInput.files[0]) {
                    console.log('选择文件:', actualFileInput.files[0].name);
                    handleFile(actualFileInput.files[0]);
                } else {
                    console.log('未选择文件');
            }
        });

            console.log('上传组件初始化完成');
        }

        // 在DOM加载完成后初始化
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initUploadHandlers);
        } else {
            // DOM已经加载完成
            initUploadHandlers();
        }

        async function handleFile(file) {
            console.log('=== 开始上传文件 ===');
            console.log('文件名:', file.name);
            console.log('文件大小:', file.size, 'bytes');
            console.log('文件类型:', file.type);

            // 检查文件大小 (500MB限制)
            const maxSize = 500 * 1024 * 1024; // 500MB
            if (file.size > maxSize) {
                alert(`文件太大！最大支持500MB，当前文件: ${(file.size / 1024 / 1024).toFixed(2)}MB`);
                return;
            }

            // 检查文件类型
            const validImageTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/bmp', 'image/webp'];
            const validVideoTypes = ['video/mp4', 'video/avi', 'video/quicktime', 'video/x-matroska', 'video/webm'];
            const fileExt = file.name.toLowerCase().split('.').pop();
            const validExts = ['jpg', 'jpeg', 'png', 'bmp', 'webp', 'mp4', 'avi', 'mov', 'mkv', 'webm'];
            
            if (!validExts.includes(fileExt) && !validImageTypes.includes(file.type) && !validVideoTypes.includes(file.type)) {
                alert('不支持的文件格式！\n支持的格式: JPG, PNG, BMP, WEBP, MP4, AVI, MOV, MKV, WEBM');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);
            formData.append('frame_skip', document.getElementById('frame-skip').value);

            document.getElementById('upload-panel').classList.add('hidden');
            document.getElementById('progress-panel').style.display = 'block';
            document.getElementById('progress-text').textContent = `正在上传文件: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)}MB)...`;

            try {
                const uploadUrl = window.location.origin + '/api/upload';
                console.log('发送POST请求到:', uploadUrl);

                // 添加超时处理
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 300000); // 5分钟超时

                const response = await fetch(uploadUrl, {
                    method: 'POST',
                    body: formData,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);
                console.log('响应状态:', response.status);

                if (!response.ok) {
                    const errText = await response.text();
                    let errorMsg = '上传失败';
                    try {
                        const errJson = JSON.parse(errText);
                        errorMsg = errJson.error || errorMsg;
                    } catch {
                        errorMsg = errText || `HTTP ${response.status}`;
                    }
                    throw new Error(errorMsg);
                }

                const result = await response.json();
                console.log('上传成功:', result);

                // 开始轮询进度
                pollProgress();
            } catch (error) {
                console.error('上传错误:', error);
                let errorMsg = '上传失败';
                if (error.name === 'AbortError') {
                    errorMsg = '上传超时，请检查网络连接或文件大小';
                } else if (error.message) {
                    errorMsg = error.message;
                } else {
                    errorMsg = '网络错误，请检查连接';
                }
                
                alert(errorMsg + '\n\n如果问题持续，请尝试:\n1. 检查网络连接\n2. 减小文件大小\n3. 使用支持的格式');
                document.getElementById('upload-panel').classList.remove('hidden');
                document.getElementById('progress-panel').style.display = 'none';
            }
        }

        async function pollProgress() {
            try {
                const response = await fetch('/api/progress');
                const status = await response.json();
                
                document.getElementById('progress-fill').style.width = status.progress + '%';
                document.getElementById('progress-text').textContent = status.message;
                
                if (status.total_frames > 0) {
                    document.getElementById('progress-detail').textContent = 
                        `帧 ${status.current_frame}/${status.total_frames} | 预计剩余: ${status.eta}`;
                }
                
                if (status.error) {
                    alert('处理失败: ' + status.error);
                    document.getElementById('upload-panel').classList.remove('hidden');
                    document.getElementById('progress-panel').style.display = 'none';
                    return;
                }
                
                if (status.result_path) {
                    // 处理完成
                    document.getElementById('progress-panel').style.display = 'none';
                    isVideoMode = status.is_video;
                    await loadResult(status.result_path);
                    return;
                }
                
                setTimeout(pollProgress, 500);
            } catch (e) {
                setTimeout(pollProgress, 1000);
            }
        }

        async function loadResult(resultPath) {
            try {
                if (isVideoMode) {
                    const resp = await fetch('/api/video_info');
                    videoInfo = await resp.json();
                    frameFiles = videoInfo.processed_frames.map(f => f.file);
                    playFPS = videoInfo.fps || 10;
                    
                    document.getElementById('frame-slider').max = frameFiles.length - 1;
                    document.getElementById('player-controls').style.display = 'flex';
                    document.getElementById('video-info-text').style.display = 'block';
                    
                    // 加载faces
                    const facesResp = await fetch('/api/faces');
                    if (facesResp.ok) sharedFaces = await facesResp.json();
                    
                    await loadFrame(0);
                } else {
                    const resp = await fetch('/api/mhr');
                    mhrData = await resp.json();
                    updateInfo();
                    createMeshes();
                }
                
                document.getElementById('info').style.display = 'block';
                document.getElementById('controls').style.display = 'block';
                document.getElementById('new-btn').style.display = 'block';
            } catch (e) {
                console.error('加载结果失败:', e);
            }
        }

        async function loadFrame(index) {
            if (index < 0 || index >= frameFiles.length) return;
            currentFrameIndex = index;
            const fileName = frameFiles[index];
            
            if (frameCache[fileName]) {
                mhrData = frameCache[fileName];
            } else {
                const resp = await fetch(`/api/frame/${fileName}`);
                mhrData = await resp.json();
                if (!mhrData.faces && sharedFaces) mhrData.faces = sharedFaces;
                if (Object.keys(frameCache).length < 50) frameCache[fileName] = mhrData;
            }
            
            updateInfo();
            createMeshes();
            
            document.getElementById('frame-slider').value = index;
            document.getElementById('frame-info').textContent = `${index+1} / ${frameFiles.length}`;
            document.getElementById('current-frame').textContent = `${index+1} / ${frameFiles.length}`;
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

        // 视频播放控制
        function togglePlay() {
            isPlaying = !isPlaying;
            document.getElementById('btn-play').textContent = isPlaying ? '⏸' : '▶';
            document.getElementById('btn-play').classList.toggle('active', isPlaying);
            if (isPlaying) playNextFrame();
        }

        async function playNextFrame() {
            if (!isPlaying || isLoadingFrame) return;
            isLoadingFrame = true;
            let next = currentFrameIndex + 1;
            if (next >= frameFiles.length) next = 0;
            await loadFrame(next);
            isLoadingFrame = false;
            if (isPlaying) setTimeout(playNextFrame, 1000 / (playFPS * playbackSpeed));
        }

        async function prevFrame() {
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            let prev = currentFrameIndex - 1;
            if (prev < 0) prev = frameFiles.length - 1;
            await loadFrame(prev);
            isLoadingFrame = false;
        }

        async function nextFrame() {
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            let next = currentFrameIndex + 1;
            if (next >= frameFiles.length) next = 0;
            await loadFrame(next);
            isLoadingFrame = false;
        }

        async function skipFrames(count) {
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            let idx = Math.max(0, Math.min(frameFiles.length - 1, currentFrameIndex + count));
            await loadFrame(idx);
            isLoadingFrame = false;
        }

        function changeSpeed(delta) {
            playbackSpeed = Math.max(0.25, Math.min(4.0, playbackSpeed + delta));
            document.getElementById('speed-display').textContent = playbackSpeed.toFixed(2) + 'x';
        }

        async function jumpToFrame() {
            const input = document.getElementById('jump-input');
            const num = parseInt(input.value);
            if (isNaN(num) || num < 1 || num > frameFiles.length) return;
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            await loadFrame(num - 1);
            isLoadingFrame = false;
            input.value = '';
        }

        function addMarker() {
            if (!isVideoMode || frameMarkers.includes(currentFrameIndex)) return;
            frameMarkers.push(currentFrameIndex);
            frameMarkers.sort((a,b) => a - b);
            updateMarkersDisplay();
            document.getElementById('markers-panel').style.display = 'block';
        }

        function updateMarkersDisplay() {
            const list = document.getElementById('markers-list');
            if (frameMarkers.length === 0) {
                list.innerHTML = '<span style="color:#666">暂无标记</span>';
                return;
            }
            list.innerHTML = frameMarkers.map(idx => 
                `<div class="marker-item" onclick="window.goToMarker(${idx})">
                    帧 ${idx+1}
                    <span class="delete-marker" onclick="event.stopPropagation();window.removeMarker(${idx})">×</span>
                </div>`
            ).join('');
        }

        window.goToMarker = async (idx) => {
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            await loadFrame(idx);
            isLoadingFrame = false;
        };

        window.removeMarker = (idx) => {
            const i = frameMarkers.indexOf(idx);
            if (i > -1) { frameMarkers.splice(i, 1); updateMarkersDisplay(); }
        };

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
        
        document.getElementById('btn-play').onclick = togglePlay;
        document.getElementById('btn-prev').onclick = prevFrame;
        document.getElementById('btn-next').onclick = nextFrame;
        document.getElementById('btn-fast-backward').onclick = () => skipFrames(-FAST_SKIP_FRAMES);
        document.getElementById('btn-fast-forward').onclick = () => skipFrames(FAST_SKIP_FRAMES);
        document.getElementById('frame-slider').oninput = async (e) => {
            if (isPlaying) { isPlaying = false; document.getElementById('btn-play').textContent = '▶'; }
            if (isLoadingFrame) return;
            isLoadingFrame = true;
            await loadFrame(parseInt(e.target.value));
            isLoadingFrame = false;
        };
        document.getElementById('btn-speed-up').onclick = () => changeSpeed(0.25);
        document.getElementById('btn-speed-down').onclick = () => changeSpeed(-0.25);
        document.getElementById('jump-btn').onclick = jumpToFrame;
        document.getElementById('jump-input').onkeydown = (e) => { if (e.code === 'Enter') jumpToFrame(); };
        document.getElementById('btn-marker').onclick = () => {
            const panel = document.getElementById('markers-panel');
            if (panel.style.display === 'block') panel.style.display = 'none';
            else { panel.style.display = 'block'; updateMarkersDisplay(); }
        };
        
        document.getElementById('btn-new').onclick = () => {
            location.reload();
        };
        
        // 摄像头相关功能
        document.getElementById('camera-btn').onclick = startCamera;
        document.getElementById('stop-camera-btn').onclick = stopCamera;
        document.getElementById('capture-btn').onclick = captureAndProcess;
        
        async function startCamera() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ 
                    video: { width: 640, height: 480 } 
                });
                cameraStream = stream;
                const video = document.getElementById('camera-video');
                video.srcObject = stream;
                
                document.getElementById('upload-panel').classList.add('hidden');
                document.getElementById('camera-panel').classList.remove('hidden');
                isCameraMode = true;
                
                // 等待视频加载
                await new Promise((resolve) => {
                    video.onloadedmetadata = () => {
                        video.play();
                        resolve();
                    };
                });
                
                // 初始化MediaPipe Hands
                // 等待MediaPipe库加载
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
                                
                                // 启动摄像头处理
                                if (typeof Camera !== 'undefined') {
                                    camera = new Camera(video, {
                                        onFrame: async () => {
                                            await hands.send({image: video});
                                        },
                                        width: 640,
                                        height: 480
                                    });
                                    camera.start();
                                } else {
                                    // 如果Camera类不可用，使用requestAnimationFrame
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
                        console.warn('MediaPipe Hands未加载，使用基础手势检测');
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
            canvas.width = 640;
            canvas.height = 480;
            ctx.drawImage(video, 0, 0, 640, 480);
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
            document.getElementById('camera-panel').classList.add('hidden');
            document.getElementById('upload-panel').classList.remove('hidden');
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
        
        async function captureAndProcess() {
            if (!cameraStream) return;
            
            const video = document.getElementById('camera-video');
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            
            canvas.toBlob(async (blob) => {
                const file = new File([blob], 'camera_capture.jpg', { type: 'image/jpeg' });
                stopCamera();
                await handleFile(file);
            }, 'image/jpeg', 0.95);
        }
        
        function onHandResults(results) {
            const canvas = document.getElementById('camera-canvas');
            const ctx = canvas.getContext('2d');
            canvas.width = 640;
            canvas.height = 480;
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
                const landmarks = results.multiHandLandmarks[0];
                const handedness = results.multiHandedness ? results.multiHandedness[0] : null;
                
                // 绘制手部关键点
                drawConnectors(ctx, landmarks, HAND_CONNECTIONS_GESTURE, {color: '#00FF00', lineWidth: 2});
                drawLandmarks(ctx, landmarks, {color: '#FF0000', lineWidth: 1, radius: 3});
                
                // 处理手势
                processGesture(landmarks, handedness);
            }
        }
        
        function processGesture(landmarks, handedness) {
            if (!meshes || meshes.length === 0) return;
            
            const now = Date.now();
            if (now - gestureState.lastGestureTime < gestureState.gestureCooldown) {
                return;
            }
            
            // 计算手指数量
            const fingerCount = countFingers(landmarks);
            
            // 获取手掌中心位置
            const wrist = landmarks[0];
            const middleMCP = landmarks[9];
            const handCenter = {
                x: (wrist.x + middleMCP.x) / 2,
                y: (wrist.y + middleMCP.y) / 2
            };
            
            // 手势1: 单指向上/下 - 缩放
            if (fingerCount === 1) {
                if (gestureState.lastHandPosition) {
                    const dy = handCenter.y - gestureState.lastHandPosition.y;
                    if (Math.abs(dy) > 0.02) {
                        if (dy < 0) {
                            // 向上滑动 - 放大
                            zoomCamera(0.9);
                        } else {
                            // 向下滑动 - 缩小
                            zoomCamera(1.1);
                        }
                        gestureState.lastGestureTime = now;
                    }
                }
            }
            
            // 手势2: 手掌张开旋转 - 旋转模型
            if (fingerCount === 5) {
                if (gestureState.lastHandPosition) {
                    const dx = handCenter.x - gestureState.lastHandPosition.x;
                    const dy = handCenter.y - gestureState.lastHandPosition.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    
                    if (distance > 0.03) {
                        // 计算旋转角度（基于水平移动）
                        const angle = dx * 30; // 放大旋转效果
                        rotateCamera(angle);
                        gestureState.lastGestureTime = now;
                    }
                }
            }
            
            // 手势3: 握拳 - 重置视角
            if (fingerCount === 0 && gestureState.lastFingerCount > 0) {
                fitCameraToMeshes();
                saveCameraState();
                gestureState.lastGestureTime = now;
            }
            
            // 手势4: 两指 - 切换显示模式
            if (fingerCount === 2 && gestureState.lastFingerCount !== 2) {
                // 循环切换: mesh -> wireframe -> skeleton -> mesh
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
            // MediaPipe Hands的21个关键点索引
            // 0: 手腕, 1-4: 拇指, 5-8: 食指, 9-12: 中指, 13-16: 无名指, 17-20: 小指
            const fingerTips = [4, 8, 12, 16, 20];
            const fingerPIPs = [3, 6, 10, 14, 18];
            const thumbIP = 2;
            const thumbMCP = 1;
            
            let count = 0;
            
            // 拇指：检查x坐标（拇指是横向的）
            if (landmarks[4].x > landmarks[3].x) {
                count++;
            }
            
            // 其他四指：检查y坐标
            for (let i = 1; i < 5; i++) {
                const tipIdx = fingerTips[i];
                const pipIdx = fingerPIPs[i];
                if (landmarks[tipIdx].y < landmarks[pipIdx].y) {
                    count++;
                }
            }
            
            return count;
        }
        
        // MediaPipe Hands连接定义（用于手势识别绘制）
        const HAND_CONNECTIONS_GESTURE = [
            [0, 1], [1, 2], [2, 3], [3, 4],
            [0, 5], [5, 6], [6, 7], [7, 8],
            [0, 9], [9, 10], [10, 11], [11, 12],
            [0, 13], [13, 14], [14, 15], [15, 16],
            [0, 17], [17, 18], [18, 19], [19, 20],
            [5, 9], [9, 13], [13, 17]
        ];
        
        // MediaPipe绘制函数（简化版）
        function drawConnectors(ctx, points, connections, options) {
            ctx.strokeStyle = options.color || '#00FF00';
            ctx.lineWidth = options.lineWidth || 2;
            ctx.beginPath();
            for (const [start, end] of connections) {
                if (start < points.length && end < points.length) {
                    ctx.moveTo(points[start].x * 640, points[start].y * 480);
                    ctx.lineTo(points[end].x * 640, points[end].y * 480);
                }
            }
            ctx.stroke();
        }
        
        function drawLandmarks(ctx, points, options) {
            ctx.fillStyle = options.color || '#FF0000';
            for (const point of points) {
                ctx.beginPath();
                ctx.arc(point.x * 640, point.y * 480, options.radius || 3, 0, 2 * Math.PI);
                ctx.fill();
            }
        }

        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT') return;
            if (e.code === 'Equal' || e.code === 'NumpadAdd') zoomCamera(0.8);
            else if (e.code === 'Minus' || e.code === 'NumpadSubtract') zoomCamera(1.25);
            else if (e.code === 'KeyQ') rotateCamera(-15);
            else if (e.code === 'KeyE') rotateCamera(15);
            
            if (!isVideoMode) return;
            if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
            else if (e.code === 'ArrowLeft' && e.shiftKey) skipFrames(-FAST_SKIP_FRAMES);
            else if (e.code === 'ArrowRight' && e.shiftKey) skipFrames(FAST_SKIP_FRAMES);
            else if (e.code === 'ArrowLeft') prevFrame();
            else if (e.code === 'ArrowRight') nextFrame();
            else if (e.code === 'KeyL') document.getElementById('btn-lock').click();
            else if (e.code === 'KeyF') setViewAngle('front');
            else if (e.code === 'KeyB') setViewAngle('back');
            else if (e.code === 'BracketLeft') changeSpeed(-0.25);
            else if (e.code === 'BracketRight') changeSpeed(0.25);
            else if (e.code === 'KeyM') addMarker();
        });

        // 初始化
        initScene();
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
                
        elif parsed.path == '/api/video_info':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            if processing_status['result_path'] and processing_status['is_video']:
                info_path = Path(processing_status['result_path']) / 'video_info.json'
                if info_path.exists():
                    with open(info_path, 'r') as f:
                        self.wfile.write(f.read().encode('utf-8'))
                        return
            self.wfile.write(b'null')
            
        elif parsed.path == '/api/faces':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            if processing_status['result_path'] and processing_status['is_video']:
                faces_path = Path(processing_status['result_path']) / 'faces.json'
                if faces_path.exists():
                    with open(faces_path, 'r') as f:
                        self.wfile.write(f.read().encode('utf-8'))
                        return
            self.wfile.write(b'null')
            
        elif parsed.path.startswith('/api/frame/'):
            frame_file = parsed.path.replace('/api/frame/', '')
            if processing_status['result_path']:
                frame_path = Path(processing_status['result_path']) / frame_file
                if frame_path.exists():
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_cors_headers()
                    self.end_headers()
                    with open(frame_path, 'r') as f:
                        self.wfile.write(f.read().encode('utf-8'))
                    return
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/upload':
            try:
                print(f"[上传] 收到POST请求")
                content_length = int(self.headers['Content-Length'])
                content_type = self.headers['Content-Type']
                print(f"[上传] Content-Length: {content_length}, Content-Type: {content_type}")

                # 读取整个请求体
                print(f"[上传] 开始读取请求体...")
                body = self.rfile.read(content_length)
                print(f"[上传] 请求体读取完成, 大小: {len(body)} bytes")

                # 解析 multipart boundary
                print(f"[上传] 解析multipart...")
                boundary = None
                for part in content_type.split(';'):
                    part = part.strip()
                    if part.startswith('boundary='):
                        boundary = part[9:].strip('"')
                        break

                if not boundary:
                    raise ValueError("No boundary found")

                print(f"[上传] 找到boundary: {boundary[:50]}...")
                boundary_bytes = boundary.encode()

                # 分割各个部分
                parts = body.split(b'--' + boundary_bytes)
                print(f"[上传] 分割得到 {len(parts)} 个部分")

                filename = None
                file_content = None
                frame_skip = 0

                for part in parts:
                    if b'Content-Disposition' not in part:
                        continue

                    # 分离头部和内容
                    if b'\r\n\r\n' in part:
                        header_section, content = part.split(b'\r\n\r\n', 1)
                    else:
                        continue

                    header_str = header_section.decode('utf-8', errors='ignore')

                    # 去掉末尾的 \r\n--
                    if content.endswith(b'\r\n'):
                        content = content[:-2]
                    if content.endswith(b'--'):
                        content = content[:-2]
                    if content.endswith(b'\r\n'):
                        content = content[:-2]

                    if 'name="file"' in header_str:
                        # 提取文件名
                        import re
                        match = re.search(r'filename="([^"]+)"', header_str)
                        if match:
                            filename = match.group(1)
                            file_content = content
                            print(f"[上传] 找到文件: {filename}, 内容大小: {len(content)} bytes")
                    elif 'name="frame_skip"' in header_str:
                        try:
                            frame_skip = int(content.decode().strip())
                        except:
                            frame_skip = 0

                if not filename or file_content is None:
                    raise ValueError("No file uploaded")

                # 保存上传文件
                upload_path = output_folder / 'uploads' / filename
                upload_path.parent.mkdir(parents=True, exist_ok=True)

                with open(upload_path, 'wb') as f:
                    f.write(file_content)

                print(f"文件已保存: {upload_path}, 大小: {len(file_content)} bytes")

                # 在后台线程处理
                thread = threading.Thread(target=process_file, args=(str(upload_path), frame_skip))
                thread.daemon = True
                thread.start()

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status": "processing"}')

            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def log_message(self, format, *args):
        # 显示完整请求信息
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
        from tools.mhr_io import save_mhr, numpy_to_list
        
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
        
        # 判断文件类型
        ext = Path(filepath).suffix.lower()
        is_image = ext in {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        is_video = ext in {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        
        if is_image:
            process_single_image(filepath, estimator)
        elif is_video:
            process_video_file(filepath, frame_skip, estimator)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        processing_status['error'] = str(e)
    finally:
        processing_status['is_processing'] = False


def process_single_image(filepath, est):
    """处理单张图片"""
    import cv2
    from tools.mhr_io import save_mhr
    
    processing_status['message'] = '正在处理图片...'
    processing_status['is_video'] = False
    
    img = cv2.imread(filepath)
    if img is None:
        raise ValueError("无法读取图片")
    
    image_size = (img.shape[1], img.shape[0])
    
    processing_status['progress'] = 30
    outputs = est.process_one_image(filepath, bbox_thr=0.8, use_mask=False)
    processing_status['progress'] = 80
    
    if not outputs:
        raise ValueError("未检测到人体")
    
    base_name = Path(filepath).stem
    mhr_path = output_folder / f"{base_name}.mhr.json"
    
    save_mhr(mhr_path, outputs, est.faces, image_path=filepath, image_size=image_size)
    
    processing_status['progress'] = 100
    processing_status['message'] = '处理完成!'
    processing_status['result_path'] = str(mhr_path)


def process_video_file(filepath, frame_skip, est):
    """处理视频"""
    import cv2
    import json
    from tools.mhr_io import save_mhr, numpy_to_list
    
    processing_status['message'] = '正在分析视频...'
    processing_status['is_video'] = True
    
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        raise ValueError("无法打开视频")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    frames_to_process = list(range(0, total_frames, frame_skip + 1))
    num_frames = len(frames_to_process)
    
    processing_status['total_frames'] = num_frames
    
    video_name = Path(filepath).stem
    video_output = output_folder / video_name
    video_output.mkdir(parents=True, exist_ok=True)
    
    video_info = {
        "video_path": filepath,
        "video_name": video_name,
        "fps": fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "frame_skip": frame_skip,
        "processed_frames": [],
    }
    
    faces_saved = False
    frame_times = []
    
    for i, frame_idx in enumerate(frames_to_process):
        frame_start = time.time()
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        try:
            outputs = est.process_one_image(frame_rgb, bbox_thr=0.8, use_mask=False)
        except:
            continue
        
        frame_time = time.time() - frame_start
        frame_times.append(frame_time)
        
        # 更新进度
        progress = 10 + int(90 * (i + 1) / num_frames)
        avg_time = sum(frame_times) / len(frame_times)
        remaining = (num_frames - i - 1) * avg_time
        
        processing_status['progress'] = progress
        processing_status['current_frame'] = i + 1
        processing_status['message'] = f'处理中... {i+1}/{num_frames}'
        
        if remaining < 60:
            processing_status['eta'] = f"{remaining:.0f}秒"
        else:
            processing_status['eta'] = f"{remaining/60:.1f}分钟"
        
        if not outputs:
            continue
        
        frame_name = f"frame_{frame_idx:06d}"
        mhr_path = video_output / f"{frame_name}.mhr.json"
        
        if not faces_saved:
            save_mhr(mhr_path, outputs, est.faces, image_path=f"frame_{frame_idx}", image_size=(width, height))
            faces_saved = True
            with open(video_output / "faces.json", 'w') as f:
                json.dump(est.faces.tolist(), f)
        else:
            # 不保存faces的版本
            mhr_data = {
                "version": "1.0",
                "image_path": f"frame_{frame_idx}",
                "image_size": [width, height],
                "num_people": len(outputs),
                "faces": None,
                "people": []
            }
            for j, person in enumerate(outputs):
                person_data = {
                    "id": j,
                    "bbox": numpy_to_list(person.get("bbox")),
                    "focal_length": float(person.get("focal_length", 500.0)),
                    "camera": {"translation": numpy_to_list(person.get("pred_cam_t"))},
                    "mesh": {
                        "vertices": numpy_to_list(person.get("pred_vertices")),
                        "keypoints_3d": numpy_to_list(person.get("pred_keypoints_3d")),
                        "keypoints_2d": numpy_to_list(person.get("pred_keypoints_2d")),
                    },
                    "params": {
                        "global_rot": numpy_to_list(person.get("global_rot")),
                        "body_pose": numpy_to_list(person.get("body_pose_params")),
                        "shape": numpy_to_list(person.get("shape_params")),
                        "scale": numpy_to_list(person.get("scale_params")),
                        "hand": numpy_to_list(person.get("hand_pose_params")),
                        "expression": numpy_to_list(person.get("expr_params")),
                    }
                }
                mhr_data["people"].append(person_data)
            with open(mhr_path, 'w') as f:
                json.dump(mhr_data, f)
        
        video_info["processed_frames"].append({
            "frame_idx": frame_idx,
            "file": f"{frame_name}.mhr.json",
            "num_people": len(outputs),
        })
    
    cap.release()
    
    with open(video_output / "video_info.json", 'w') as f:
        json.dump(video_info, f, indent=2)
    
    processing_status['progress'] = 100
    processing_status['message'] = '处理完成!'
    processing_status['result_path'] = str(video_output)


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
    parser = argparse.ArgumentParser(description="3D人体重建 Demo")
    parser.add_argument("--port", type=int, default=8080, help="服务器端口")
    parser.add_argument("--output", default="./output", help="输出目录")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--ssl", action="store_true", help="启用HTTPS (需要证书)")
    parser.add_argument("--cert", default="cert.pem", help="SSL证书文件路径 (默认: cert.pem)")
    parser.add_argument("--key", default="key.pem", help="SSL私钥文件路径 (默认: key.pem)")
    parser.add_argument("--auto-cert", action="store_true", help="自动生成自签名证书 (需要cryptography库)")
    args = parser.parse_args()

    global output_folder
    output_folder = Path(args.output)
    output_folder.mkdir(parents=True, exist_ok=True)

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

    # 使用多线程服务器，避免上传时阻塞其他请求
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
        print(f"3D人体重建 Demo 已启动!")
        if use_ssl:
            print(f"\n[HTTPS模式] 摄像头功能可在远程使用")
            print(f"注意: 自签名证书需要在浏览器中手动信任")
        print(f"\n本地访问: {protocol}://localhost:{port}")
        print(f"远程访问: {protocol}://{local_ip}:{port}")
        print(f"\n按 Ctrl+C 停止服务器")
        print(f"{'='*50}\n")

        # 只在本地时自动打开浏览器
        if args.host in ('localhost', '127.0.0.1'):
            threading.Timer(1.0, lambda: webbrowser.open(f"{protocol}://localhost:{port}")).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")


if __name__ == "__main__":
    main()
