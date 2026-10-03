import cv2
import numpy as np
import pyautogui
import time
import winsound
import sys
from collections import deque
import threading

# ============================================
# CONFIGURATION - Set these to your VPS coordinates
# ============================================

# Game window region (x, y, width, height)
GAME_REGION = (0, 0, 800, 600)  # Adjust to your game window

# Scouting window region (the "Scouting by Louten" window)
SCOUT_REGION = (100, 700, 300, 400)  # Adjust to your scouting window position

# Loading text region (upper left where "Loading - please wait" appears)
LOADING_REGION = (10, 80, 200, 30)  # Upper left area

# Alarm sound file (optional - if None, uses beep)
ALARM_SOUND = "alarm.wav"  # Set to None for default beep

# Delay settings (in seconds)
DELAY_BETWEEN_CLICKS = 0.5
DELAY_AFTER_HOP = 2.0
DELAY_BETWEEN_PLAYERS = 0.3

# ============================================
# MAIN BOT CLASS
# ============================================

class SimpleScoutBot:
    def __init__(self):
        self.checked_players = set()  # Track checked players by position hash
        self.running = True
        self.current_world_players = []
        
        # Safety: move mouse to corner so it doesn't interfere
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        
    def capture_region(self, region):
        """Capture specific screen region"""
        x, y, w, h = region
        screenshot = pyautogui.screenshot(region=(x, y, w, h))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    
    def is_loading(self):
        """Check if 'Loading - please wait' is present"""
        img = self.capture_region(LOADING_REGION)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Check for white text on dark background
        # Loading text is bright white
        white_pixels = np.sum(gray > 200)
        total_pixels = gray.size
        
        # If significant white pixels, loading is active
        return white_pixels > (total_pixels * 0.1)
    
    def wait_for_load(self):
        """Wait for loading to complete"""
        print("Waiting for world to load...")
        
        # First wait for loading to appear
        timeout = 0
        while not self.is_loading() and timeout < 50:
            time.sleep(0.1)
            timeout += 1
        
        # Then wait for it to disappear
        while self.is_loading():
            time.sleep(0.2)
        
        time.sleep(0.5)  # Extra safety buffer
        print("World loaded!")
    
    def hop_world(self):
        """Press right arrow and wait"""
        print("Hopping to next world...")
        self.checked_players.clear()
        
        pyautogui.keyDown('right')
        pyautogui.keyUp('right')
        
        self.wait_for_load()
        time.sleep(DELAY_AFTER_HOP)
    
    def find_cyan_name_tags(self):
        """Find all cyan name tags (player indicators)"""
        game_img = self.capture_region(GAME_REGION)
        hsv = cv2.cvtColor(game_img, cv2.COLOR_BGR2HSV)
        
        # Cyan color range in HSV
        # Cyan is around hue 90-100
        lower_cyan = np.array([80, 100, 150])
        upper_cyan = np.array([100, 255, 255])
        
        mask = cv2.inRange(hsv, lower_cyan, upper_cyan)
        
        # Clean up noise
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        players = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Filter by size (name tags are small)
            if 15 < w < 120 and 5 < h < 25:
                # Calculate click position (below the name tag, where body is)
                click_x = GAME_REGION[0] + x + w // 2
                click_y = GAME_REGION[1] + y + h + 20  # Below the name
                
                # Create a simple hash of position to track unique players
                pos_hash = f"{x//10}_{y//10}"  # Rough grouping
                
                players.append({
                    'click_pos': (click_x, click_y),
                    'hash': pos_hash,
                    'bbox': (x, y, w, h)
                })
        
        return players
    
    def count_players(self):
        """Count and return player positions"""
        players = self.find_cyan_name_tags()
        return len(players), players
    
    def double_right_click(self, x, y):
        """Double right-click on player"""
        # Move to position
        pyautogui.moveTo(x, y, duration=0.1)
        time.sleep(0.05)
        
        # First right-click
        pyautogui.rightClick(x, y)
        time.sleep(0.05)
        
        # Second right-click
        pyautogui.rightClick(x, y)
        time.sleep(DELAY_BETWEEN_CLICKS)
    
    def get_scouting_entry_color(self):
        """
        Check the scouting window for new entries and their border colors
        Returns: 'green', 'red', 'white', or None
        """
        scout_img = self.capture_region(SCOUT_REGION)
        hsv = cv2.cvtColor(scout_img, cv2.COLOR_BGR2HSV)
        
        # Define color ranges for border detection
        
        # Green border (success - target found!)
        lower_green = np.array([35, 50, 50])
        upper_green = np.array([85, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_pixels = cv2.countNonZero(green_mask)
        
        # Red border (already in leechlist or unavailable)
        lower_red1 = np.array([0, 100, 50])
        upper_red1 = np.array([15, 255, 255])
        lower_red2 = np.array([165, 100, 50])
        upper_red2 = np.array([180, 255, 255])
        red_mask = cv2.inRange(hsv, lower_red1, upper_red1) + cv2.inRange(hsv, lower_red2, upper_red2)
        red_pixels = cv2.countNonZero(red_mask)
        
        # White/gray border (no good items or checked)
        lower_white = np.array([0, 0, 180])
        upper_white = np.array([180, 30, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)
        white_pixels = cv2.countNonZero(white_mask)
        
        # Determine dominant color (thresholds may need tuning)
        if green_pixels > 500:
            return 'green'
        elif red_pixels > 500:
            return 'red'
        elif white_pixels > 500:
            return 'white'
        
        return None
    
    def play_alarm(self, message="TARGET FOUND!"):
        """Play alarm and stop bot"""
        print(f"\n{'='*50}")
        print(f"ALARM: {message}")
        print(f"{'='*50}\n")
        
        # Play sound repeatedly
        for _ in range(5):
            if ALARM_SOUND:
                try:
                    import playsound
                    playsound.playsound(ALARM_SOUND, block=False)
                except:
                    winsound.Beep(1000, 500)
            else:
                winsound.Beep(1000, 500)
                winsound.Beep(1500, 500)
            time.sleep(0.2)
        
        self.running = False
    
    def check_player(self, player):
        """Check a single player"""
        pos = player['click_pos']
        player_hash = player['hash']
        
        # Skip if already checked
        if player_hash in self.checked_players:
            return False
        
        print(f"Checking player at {pos}...")
        
        try:
            # Double right-click
            self.double_right_click(pos[0], pos[1])
            
            # Wait for scouting window to update
            time.sleep(0.3)
            
            # Check scouting window color
            color = self.get_scouting_entry_color()
            
            if color == 'green':
                print("GREEN BORDER FOUND!")
                self.play_alarm("GREEN BORDER PLAYER FOUND!")
                return True  # Signal to stop
            
            elif color in ['red', 'white']:
                print(f"Border color: {color} - adding to checked list")
                self.checked_players.add(player_hash)
                return False
            
            else:
                print("No color detected - may need to adjust")
                return False
                
        except Exception as e:
            print(f"Error checking player: {e}")
            self.play_alarm(f"ERROR: {e}")
            return True  # Stop on error
    
    def run(self):
        """Main bot loop"""
        print("="*50)
        print("RUNESCAPE SCOUT BOT STARTED")
        print("="*50)
        print(f"Game region: {GAME_REGION}")
        print(f"Scout region: {SCOUT_REGION}")
        print(f"Loading region: {LOADING_REGION}")
        print("Press Ctrl+C to stop")
        print("="*50)
        
        try:
            while self.running:
                # Step 1: Count players
                count, players = self.count_players()
                print(f"\nFound {count} players in lobby")
                
                # Step 2: Check if should hop
                if count > 5 or count == 0:
                    print("Too many or no players - hopping worlds")
                    self.hop_world()
                    continue
                
                # Step 3: Check each player
                found_target = False
                for player in players:
                    if not self.running:
                        break
                    
                    found_target = self.check_player(player)
                    
                    if found_target:
                        break  # Stop everything
                    
                    time.sleep(DELAY_BETWEEN_PLAYERS)
                
                if not self.running:
                    break
                
                # Step 4: All checked, hop to next world
                if not found_target:
                    print("All players checked - hopping worlds")
                    self.hop_world()
                
        except KeyboardInterrupt:
            print("\nBot stopped by user")
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            self.play_alarm(f"UNEXPECTED ERROR: {e}")
        
        print("Bot shutdown complete")

# ============================================
# RUN THE BOT
# ============================================

if __name__ == "__main__":
    bot = SimpleScoutBot()
    bot.run()