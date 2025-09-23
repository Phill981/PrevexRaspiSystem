import cv2
import time
import numpy as np
from datetime import datetime
import os
import requests
import json
import uuid
import glob
import hashlib

class RaspberryPiSystem:
    def __init__(self, device_id=None, api_url="http://c4kgwso4ggcgk44080kc4ooo.157.90.23.234.sslip.io", temp_dir="temp_storage"):
        self.device_id = device_id or self._generate_device_id()
        self.api_url = api_url
        self.temp_dir = temp_dir
        self.last_heartbeat = None
        
        # Create temp directory
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Clean up temp storage on startup
        self.cleanup_temp_storage()
        
        print(f"Raspberry Pi System initialized with ID: {self.device_id}")
    
    def _generate_device_id(self):
        """Generate a unique device identifier"""
        # Use MAC address and system info to create a unique ID
        try:
            # Try to get MAC address
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) 
                           for ele in range(0,8*6,8)][::-1])
            return hashlib.md5(f"{mac}-{os.uname().nodename}".encode()).hexdigest()[:12]
        except:
            # Fallback to random UUID
            return str(uuid.uuid4())[:12]
    
    def cleanup_temp_storage(self):
        """Clean up temporary storage and check for orphaned images on server"""
        print("Cleaning up temporary storage...")
        
        # Clean local temp files
        temp_files = glob.glob(os.path.join(self.temp_dir, "*.png"))
        for file_path in temp_files:
            try:
                os.remove(file_path)
                print(f"Removed local temp file: {file_path}")
            except Exception as e:
                print(f"Error removing {file_path}: {e}")
        
        # Check with server for orphaned images
        try:
            response = requests.post(f"{self.api_url}/api/cleanup-orphaned", 
                                  json={"device_id": self.device_id})
            if response.status_code == 200:
                result = response.json()
                print(f"Server cleanup completed: {result.get('message', 'Unknown')}")
            else:
                print(f"Server cleanup failed: {response.status_code}")
        except Exception as e:
            print(f"Could not contact server for cleanup: {e}")
    
    def send_heartbeat(self):
        """Send heartbeat to API to indicate device is online"""
        try:
            response = requests.post(f"{self.api_url}/api/heartbeat", 
                                  json={"device_id": self.device_id, "status": "online"})
            if response.status_code == 200:
                self.last_heartbeat = datetime.now()
                print(f"Heartbeat sent successfully at {self.last_heartbeat}")
                return True
            else:
                print(f"Heartbeat failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Heartbeat error: {e}")
            return False
    
    def upload_image(self, image_path):
        """Upload image to API"""
        try:
            with open(image_path, 'rb') as f:
                files = {'image': f}
                data = {'device_id': self.device_id}
                response = requests.post(f"{self.api_url}/api/upload-image", 
                                      files=files, data=data)
            
            if response.status_code == 200:
                print(f"Image uploaded successfully: {os.path.basename(image_path)}")
                return True
            else:
                print(f"Image upload failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Image upload error: {e}")
            return False
    
    def capture_screen(self, device="/dev/video0", interval=5, output_dir="screenshots"):
        """
        Captures a screen from a video device at a specified interval.
        The function checks if the captured image is completely black.
        If it is, the image is not saved.
        """
        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Initialize video capture from the specified device
        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            print(f"Error: Could not open video device {device}.")
            return

        print("Screen capture process started. Press Ctrl+C to stop.")
        
        # Send initial heartbeat
        self.send_heartbeat()
        
        try:
            while True:
                # Read a frame from the video capture device
                ret, frame = cap.read()
                
                # Check if the frame was read successfully
                if not ret:
                    print("Error: Could not read a frame. Exiting.")
                    break

                # Check if the image is completely black
                if frame.sum() == 0:
                    print("Captured image is completely black. Skipping save.")
                    time.sleep(interval)
                    continue

                # Generate filename with device ID and timestamp
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{self.device_id}-{ts}.png"
                filepath = os.path.join(output_dir, filename)
                temp_filepath = os.path.join(self.temp_dir, filename)
                
                # Save the frame to both permanent and temp locations
                cv2.imwrite(filepath, frame)
                cv2.imwrite(temp_filepath, frame)
                
                print(f"Screenshot saved: {filename}")
                
                # Upload image to API
                if self.upload_image(filepath):
                    # If upload successful, remove temp file
                    try:
                        os.remove(temp_filepath)
                        print(f"Removed temp file after successful upload: {filename}")
                    except Exception as e:
                        print(f"Error removing temp file: {e}")
                else:
                    print(f"Upload failed, keeping temp file: {filename}")
                
                # Send heartbeat every 30 seconds
                if not self.last_heartbeat or (datetime.now() - self.last_heartbeat).seconds > 30:
                    self.send_heartbeat()
                
                # Wait for the interval
                time.sleep(interval)

        except KeyboardInterrupt:
            print("Stopped by user.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            # Send offline status
            try:
                requests.post(f"{self.api_url}/api/heartbeat", 
                            json={"device_id": self.device_id, "status": "offline"})
            except:
                pass
            
            # Release the video capture and destroy all OpenCV windows
            cap.release()
            cv2.destroyAllWindows()

# Run the screen capture function
if __name__ == "__main__":
    # Initialize the Raspberry Pi system
    pi_system = RaspberryPiSystem()
    
    # Start capturing screens
    pi_system.capture_screen()
