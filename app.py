from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import cv2
import numpy as np
import json
import time
import os
import base64
from PIL import Image
import threading
from queue import Queue
from detection_model import EmergencyDetectionSystem

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=False,
    engineio_logger=False
)

# Global variables
detection_system = None
frame_queue = Queue(maxsize=3)
alert_queue = Queue()
is_monitoring = False

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('alerts', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        filename = f"uploaded_video_{int(time.time())}.mp4"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        return jsonify({'success': True, 'filepath': filepath})

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Client connected: {request.sid}")
    emit('connected', {'status': 'Connected'})

@socketio.on('start_monitoring')
def handle_start_monitoring(data):
    global detection_system, is_monitoring
    
    try:
        source_type = data.get('type', 'file')
        
        if source_type == 'file':
            uploaded_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.mp4')]
            if uploaded_files:
                video_source = os.path.join(app.config['UPLOAD_FOLDER'], uploaded_files[-1])
            else:
                emit('monitoring_error', {'error': 'No uploaded video found'})
                return
        else:
            video_source = data.get('source')
        
        detection_system = EmergencyDetectionSystem()
        is_monitoring = True
        
        # Start threads
        detection_thread = threading.Thread(target=run_detection_loop, args=(video_source,))
        streaming_thread = threading.Thread(target=run_streaming_loop)
        alert_thread = threading.Thread(target=run_alert_loop)
        
        detection_thread.daemon = True
        streaming_thread.daemon = True
        alert_thread.daemon = True
        
        detection_thread.start()
        streaming_thread.start()
        alert_thread.start()
        
        emit('monitoring_started', {'status': 'success'})
        
    except Exception as e:
        emit('monitoring_error', {'error': str(e)})

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    global is_monitoring
    is_monitoring = False
    emit('monitoring_stopped', {'status': 'stopped'})

def run_detection_loop(video_source):
    """Optimized detection loop with debugging"""
    global is_monitoring, detection_system, frame_queue
    
    print(f"🎬 Starting optimized detection on: {video_source}")
    cap = cv2.VideoCapture(video_source)
    
    if not cap.isOpened():
        socketio.emit('monitoring_error', {'error': f'Cannot open: {video_source}'})
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"📹 Video - FPS: {fps}, Frames: {total_frames}")
    
    frame_count = 0
    detection_count = 0
    skip_frames = 2  # Process every 3rd frame
    
    try:
        while is_monitoring:
            ret, frame = cap.read()
            if not ret:
                print("📄 End of video file reached")
                break
            
            frame_count += 1
            
            # Skip frames for performance
            if frame_count % skip_frames != 0:
                continue
            
            # For live streams: Alternative buffer management
            if isinstance(video_source, str) and video_source.startswith('rtsp'):
                for _ in range(2):
                    cap.grab()
            
            # Resize for optimal YOLO performance
            original_height, original_width = frame.shape[:2]
            inference_frame = cv2.resize(frame, (640, 640))
            display_frame = cv2.resize(frame, (640, 480))
            
            # YOLO inference
            start_time = time.time()
            results = detection_system.yolo(inference_frame, verbose=False)
            inference_time = time.time() - start_time
            
            # Process detections
            detections = []
            for result in results:
                if hasattr(result, "boxes") and result.boxes is not None:
                    for box in result.boxes:
                        confidence = float(box.conf.item())
                        class_id = int(box.cls.item())
                        class_name = detection_system.yolo.names[class_id].lower()
                        
                        if class_name == "slight":
                            continue
                        
                        # DEBUG: Add threshold debugging
                        threshold = detection_system.get_confidence_threshold(class_name)
                        
                        print(f"🔍 DEBUG: {class_name} - conf={confidence:.3f}, thresh={threshold:.3f}")
                        
                        # FIXED: Use proper comparison operators
                        if confidence < threshold:
                            print(f"❌ REJECTED: {confidence:.3f} < {threshold:.3f}")
                            continue
                            
                        print(f"✅ ACCEPTED: {confidence:.3f} >= {threshold:.3f}")
                        
                        # Get coordinates and scale
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        scale_x = original_width / 640
                        scale_y = original_height / 640
                        
                        x1_orig = int(x1 * scale_x)
                        y1_orig = int(y1 * scale_y)
                        x2_orig = int(x2 * scale_x)
                        y2_orig = int(y2 * scale_y)
                        
                        # Scale to display frame
                        display_scale_x = 640 / original_width
                        display_scale_y = 480 / original_height
                        x1_disp = int(x1_orig * display_scale_x)
                        y1_disp = int(y1_orig * display_scale_y)
                        x2_disp = int(x2_orig * display_scale_x)
                        y2_disp = int(y2_orig * display_scale_y)
                        
                        detection_data = {
                            'class_name': class_name,
                            'confidence': confidence,
                            'bbox': [x1_orig, y1_orig, x2_orig, y2_orig]
                        }
                        detections.append(detection_data)
                        detection_count += 1
                        
                        # Draw detection on display frame
                        color = get_color_for_class(class_name)
                        cv2.rectangle(display_frame, (x1_disp, y1_disp), (x2_disp, y2_disp), color, 2)
                        
                        # Add label with background
                        label = f"{class_name.upper()} {confidence:.2f}"
                        (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                        cv2.rectangle(display_frame, (x1_disp, y1_disp - label_h - 10),
                                    (x1_disp + label_w, y1_disp), color, -1)
                        cv2.putText(display_frame, label, (x1_disp, y1_disp - 5),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
                        
                        # Queue alert for processing
                        if detection_system.should_send_alert(class_name):
                            alert_data = {
                                'frame': frame.copy(),
                                'bbox': [x1_orig, y1_orig, x2_orig, y2_orig],
                                'class_name': class_name,
                                'confidence': confidence
                            }
                            try:
                                alert_queue.put_nowait(alert_data)
                                print(f"🚨 Queued alert for {class_name}")
                            except:
                                print("Alert queue full, skipping...")
            
            # Add performance overlay
            fps_actual = 1 / inference_time if inference_time > 0 else 0
            cv2.putText(display_frame, f"Inference: {fps_actual:.1f}FPS | Frame: {frame_count}",
                       (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Detections: {detection_count}",
                       (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Queue frame for streaming
            frame_data = {
                'frame': display_frame,
                'frame_count': frame_count,
                'detections': detections,
                'inference_time': inference_time,
                'fps': fps_actual
            }
            
            # Non-blocking frame queuing
            try:
                if not frame_queue.full():
                    frame_queue.put_nowait(frame_data)
                else:
                    try:
                        frame_queue.get_nowait()
                        frame_queue.put_nowait(frame_data)
                    except:
                        pass
            except:
                pass
            
            time.sleep(0.01)
            
    except Exception as e:
        print(f"❌ Detection error: {e}")
        socketio.emit('monitoring_error', {'error': str(e)})
    finally:
        cap.release()
        print(f"🏁 Detection finished. {frame_count} frames, {detection_count} detections")
        socketio.emit('monitoring_stopped', {'status': 'stopped'})

def run_streaming_loop():
    """Stream frames to frontend"""
    global is_monitoring, frame_queue
    
    while is_monitoring:
        try:
            if not frame_queue.empty():
                frame_data = frame_queue.get_nowait()
                
                # Encode frame
                _, buffer = cv2.imencode('.jpg', frame_data['frame'], 
                                       [cv2.IMWRITE_JPEG_QUALITY, 75])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # Emit to frontend
                socketio.emit('video_frame', {
                    'frame': frame_base64,
                    'frame_count': frame_data['frame_count'],
                    'detections': frame_data['detections'],
                    'fps': f"{frame_data['fps']:.1f}",
                    'inference_time': f"{frame_data['inference_time']*1000:.1f}ms"
                })
                
            time.sleep(0.033)  # ~30 FPS streaming
            
        except Exception as e:
            print(f"Streaming error: {e}")
            time.sleep(0.1)

def run_alert_loop():
    """Process emergency alerts"""
    global is_monitoring, alert_queue, detection_system
    
    while is_monitoring:
        try:
            if not alert_queue.empty():
                alert_data = alert_queue.get()
                print(f"🤖 Processing alert for {alert_data['class_name']}")
                process_emergency_alert(
                    alert_data['frame'],
                    alert_data['bbox'],
                    alert_data['class_name'],
                    alert_data['confidence']
                )
            else:
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Alert processing error: {e}")
            time.sleep(0.1)

def process_emergency_alert(frame, bbox, class_name, confidence):
    """Process and emit emergency alerts with message sending"""
    try:
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        
        # Extract incident region
        pad = 30
        x1_pad = max(0, x1 - pad)
        y1_pad = max(0, y1 - pad)
        x2_pad = min(w, x2 + pad)
        y2_pad = min(h, y2 + pad)
        
        incident_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]
        
        # Resize if too large
        if incident_crop.shape[0] > 400 or incident_crop.shape[1] > 400:
            incident_crop = cv2.resize(incident_crop, (400, 400))
        
        incident_rgb = cv2.cvtColor(incident_crop, cv2.COLOR_BGR2RGB)
        incident_pil = Image.fromarray(incident_rgb)
        
        # Notify frontend of AI processing
        socketio.emit('alert_processing', {
            'type': class_name,
            'status': 'Getting AI analysis...'
        })
        
        # Get Gemini analysis
        start_ai = time.time()
        gemini_analysis = detection_system.get_gemini_analysis(incident_pil, class_name)
        ai_time = time.time() - start_ai
        
        # Save alert
        detection_system.save_emergency_alert(class_name, confidence, gemini_analysis, incident_crop)
        
        # CREATE ALERT MESSAGE LIKE BEFORE
        alert_message = f"""
🚨 EMERGENCY ALERT #{detection_system.alert_count} 🚨
TYPE: {class_name.upper()} | CONFIDENCE: {confidence:.1%}
TIME: {time.strftime("%Y-%m-%d %H:%M:%S")}
ANALYSIS: {gemini_analysis}
ALERT ID: EMRG-{detection_system.alert_count:04d}
AI PROCESSING TIME: {ai_time:.1f}s
        """.strip()
        
        # SEND ALERT MESSAGE (like before)
        print(alert_message)
        print("-" * 60)
        
        # Optional: Send to external systems (email, SMS, etc.)
        # send_to_email(alert_message)
        # send_to_sms(alert_message)
        # send_to_slack(alert_message)
        
        # Encode image for web
        _, buffer = cv2.imencode('.jpg', incident_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        incident_image = base64.b64encode(buffer).decode('utf-8')
        
        # Emit emergency alert to frontend
        socketio.emit('emergency_alert', {
            'type': class_name.upper(),
            'confidence': confidence,
            'analysis': gemini_analysis,
            'alert_message': alert_message,  # Added full message
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'image': incident_image,
            'alert_id': f"EMRG-{detection_system.alert_count:04d}",
            'ai_time': f"{ai_time:.1f}s"
        })
        
        print(f"✅ Alert emitted: {class_name.upper()} - {confidence:.1%}")
        
    except Exception as e:
        print(f"❌ Alert error: {e}")
        socketio.emit('alert_error', {'error': str(e)})

def get_color_for_class(class_name):
    colors = {
        'severe': (0, 0, 255),     # Red
        'moderate': (0, 165, 255), # Orange  
        'fall': (0, 255, 255)      # Yellow
    }
    return colors.get(class_name, (255, 255, 255))

@app.route('/alerts/<filename>')
def serve_alert_file(filename):
    return send_from_directory('alerts', filename)

# Optional: Add external messaging functions
def send_to_email(message):
    """Send alert via email"""
    # Implement email sending logic here
    pass

def send_to_sms(message):
    """Send alert via SMS"""
    # Implement SMS sending logic here
    pass

def send_to_slack(message):
    """Send alert to Slack"""
    # Implement Slack webhook logic here
    pass

if __name__ == '__main__':
    import eventlet
    eventlet.monkey_patch()
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)
