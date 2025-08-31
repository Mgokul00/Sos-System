import os
import time
import json
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO
import google.generativeai as genai

class EmergencyDetectionSystem:
    def __init__(self):
        # Configuration
        self.yolo_model_path = r"C:\Users\MG\Downloads\best (1).pt"
        self.output_folder = "./alerts"
        
        # Detection thresholds
        self.severe_confidence = 0.70
        self.moderate_confidence = 0.70
        self.fall_confidence = 0.77
        
        # Google Gemini API
        self.google_api_key = "AIzaSyBMRUrfEMP8MqvnX1zgPeOeHDHVSCFJTW4"
        self.gemini_model = "gemini-2.5-flash"
        
        # System settings
        self.alert_cooldown = 5
        self.alert_count = 0
        self.last_alert_time = {}
        
        # Fallback messages
        self.severe_fallback = "Severe incident detected - immediate emergency response required"
        self.moderate_fallback = "Moderate incident detected - emergency assistance needed"
        self.fall_fallback = "Person has fallen - medical assistance required"
        
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Initialize Gemini
        self.use_gemini = True
        try:
            genai.configure(api_key=self.google_api_key)
            self.model = genai.GenerativeModel(self.gemini_model)
        except Exception as e:
            print(f"Failed to initialize Gemini: {e}")
            self.use_gemini = False
            self.model = None
        
        # Initialize YOLO
        self.yolo = YOLO(self.yolo_model_path)
        
        # Initialize cooldown tracking
        for class_name in ['severe', 'moderate', 'fall']:
            self.last_alert_time[class_name] = 0
    
    def get_gemini_analysis(self, image_pil, event_type):
        """Get emergency analysis from Google Gemini"""
        if not self.use_gemini or not self.model:
            return self.get_fallback_message(event_type)
        
        try:
            if event_type.lower() == "severe":
                prompt = "Analyze this severe emergency incident. Provide a brief 2-sentence report for first responders focusing on immediate hazards and required response level."
            elif event_type.lower() == "moderate":
                prompt = "Analyze this moderate emergency incident. Provide a brief 2-sentence report for first responders focusing on the situation and recommended response."
            else:  # fall
                prompt = "Analyze this fall incident. Provide a brief 2-sentence report for first responders focusing on the person's condition and immediate medical needs."
            
            response = self.model.generate_content([prompt, image_pil])
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"Gemini error: {str(e)}")
        
        return self.get_fallback_message(event_type)
    
    def get_fallback_message(self, event_type):
        """Get appropriate fallback message"""
        if event_type.lower() == "severe":
            return self.severe_fallback
        elif event_type.lower() == "moderate":
            return self.moderate_fallback
        elif event_type.lower() == "fall":
            return self.fall_fallback
        else:
            return "Emergency incident detected - response required"
    
    def get_confidence_threshold(self, event_type):
        """Get confidence threshold for incident type"""
        if event_type.lower() == "severe":
            return self.severe_confidence
        elif event_type.lower() == "moderate":
            return self.moderate_confidence
        elif event_type.lower() == "fall":
            return self.fall_confidence
        else:
            return 0.5
    
    def should_send_alert(self, event_type):
        """Check alert cooldown per incident type"""
        current_time = time.time()
        
        if event_type not in self.last_alert_time:
            self.last_alert_time[event_type] = 0
        
        time_since_last = current_time - self.last_alert_time[event_type]
        
        if time_since_last >= self.alert_cooldown:
            self.last_alert_time[event_type] = current_time
            return True
        else:
            return False
    
    def save_emergency_alert(self, event_type, confidence, gemini_analysis, image_bgr):
        """Save comprehensive emergency alert"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.alert_count += 1
        
        # Save evidence image
        image_filename = f"alert_{self.alert_count}_{event_type}_{timestamp}.jpg"
        image_path = os.path.join(self.output_folder, image_filename)
        cv2.imwrite(image_path, image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        # Create emergency report
        emergency_report = {
            "alert_id": f"EMRG-{self.alert_count:04d}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "incident_type": event_type.upper(),
            "detection_confidence": round(confidence, 3),
            "ai_analysis": gemini_analysis,
            "evidence_file": image_filename,
            "detection_threshold": self.get_confidence_threshold(event_type)
        }
        
        # Save JSON report
        report_filename = f"report_{self.alert_count}_{event_type}_{timestamp}.json"
        report_path = os.path.join(self.output_folder, report_filename)
        
        with open(report_path, "w") as f:
            json.dump(emergency_report, f, indent=2)
        
        return emergency_report
