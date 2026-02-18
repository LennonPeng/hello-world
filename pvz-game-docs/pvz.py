#!/usr/bin/env python3
"""
植物大战僵尸 - Python版
使用 Pygame 开发
"""
import pygame
import random
import sys

# 初始化
pygame.init()

# 常量配置
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 600
GRID_SIZE = 80
GRID_COLS = 9
GRID_ROWS = 5

# 颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (34, 139, 34)
LIGHT_GREEN = (144, 238, 144)
BROWN = (139, 69, 19)
YELLOW = (255, 215, 0)
RED = (220, 20, 60)
BLUE = (30, 144, 255)
GRAY = (128, 128, 128)

# 设置屏幕
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("植物大战僵尸")
clock = pygame.time.Clock()

# 资源路径
ASSETS_DIR = "assets"

# ========== 资源加载 ==========
def load_image(name, width=None, height=None):
    """加载图片"""
    try:
        img = pygame.image.load(f"{ASSETS_DIR}/{name}.png")
        if width and height:
            img = pygame.transform.scale(img, (width, height))
        return img
    except:
        # 创建临时图形
        surf = pygame.Surface((GRID_SIZE-10, GRID_SIZE-10))
        surf.fill(GREEN)
        return surf

# ========== 游戏类 ==========
class Plant:
    """植物基类"""
    def __init__(self, x, y, hp=100):
        self.x = x
        self.y = y
        self.hp = hp
        self.max_hp = hp
        self.last_action = 0
        self.cost = 0
    
    def draw(self, surface):
        # 绘制植物
        rect = pygame.Rect(self.x + 5, self.y + 5, GRID_SIZE - 10, GRID_SIZE - 10)
        pygame.draw.rect(surface, GREEN, rect)
        
        # 绘制血条
        hp_ratio = self.hp / self.max_hp
        pygame.draw.rect(surface, RED, (self.x + 5, self.y, int((GRID_SIZE-10) * hp_ratio), 5))
    
    def update(self):
        pass

class Peashooter(Plant):
    """豌豆射手"""
    def __init__(self, x, y):
        super().__init__(x, y, hp=100)
        self.cost = 100
        self.cooldown = 1500  # 发射间隔(ms)
    
    def can_shoot(self, current_time):
        return current_time - self.last_action >= self.cooldown
    
    def shoot(self, current_time):
        self.last_action = current_time
        return Pea(self.x + GRID_SIZE, self.y + GRID_SIZE // 2)

class Sunflower(Plant):
    """向日葵"""
    def __init__(self, x, y):
        super().__init__(x, y, hp=80)
        self.cost = 50
        self.cooldown = 5000  # 生产阳光间隔
    
    def can_produce(self, current_time):
        return current_time - self.last_action >= self.cooldown
    
    def produce(self, current_time):
        self.last_action = current_time
        return Sun(self.x + GRID_SIZE // 2, self.y + GRID_SIZE // 2)

class WallNut(Plant):
    """坚果墙"""
    def __init__(self, x, y):
        super().__init__(x, y, hp=400)
        self.cost = 50

class SnowPea(Plant):
    """寒冰射手"""
    def __init__(self, x, y):
        super().__init__(x, y, hp=100)
        self.cost = 175
        self.cooldown = 1500
    
    def can_shoot(self, current_time):
        return current_time - self.last_action >= self.cooldown
    
    def shoot(self, current_time):
        self.last_action = current_time
        return IcePea(self.x + GRID_SIZE, self.y + GRID_SIZE // 2)

class CherryBomb(Plant):
    """樱桃炸弹"""
    def __init__(self, x, y):
        super().__init__(x, y, hp=1)
        self.cost = 150
        self.exploded = False
    
    def explode(self):
        self.exploded = True
        return Explosion(self.x + GRID_SIZE // 2, self.y + GRID_SIZE // 2)

# ========== 子弹类 ==========
class Pea:
    """豌豆"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.speed = 8
        self.damage = 20
        self.radius = 8
        self.frozen = False
    
    def move(self):
        self.x += self.speed
    
    def draw(self, surface):
        color = BLUE if not self.frozen else (100, 200, 255)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), self.radius)
    
    def is_off_screen(self):
        return self.x > SCREEN_WIDTH

class IcePea(Pea):
    """冰豌豆"""
    def __init__(self, x, y):
        super().__init__(x, y)
        self.damage = 20
        self.frozen = True

class Explosion:
    """爆炸效果"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.radius = 10
        self.max_radius = 150
        self.expanding = True
        self.damage = 1800
        self.done = False
    
    def update(self):
        if self.expanding:
            self.radius += 15
            if self.radius >= self.max_radius:
                self.expanding = False
        else:
            self.radius -= 10
            if self.radius <= 0:
                self.done = True
    
    def draw(self, surface):
        color = (255, 50, 0)
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(self.radius))

# ========== 僵尸类 ==========
class Zombie:
    """僵尸"""
    def __init__(self, row, hp=100):
        self.x = SCREEN_WIDTH + random.randint(0, 100)
        self.y = row * GRID_SIZE + 10
        self.hp = hp
        self.max_hp = hp
        self.speed = 0.5
        self.damage = 10
        self.row = row
        self.eating = False
        self.frozen = False
        self.frozen_timer = 0
    
    def move(self):
        if not self.eating:
            speed = self.speed * 0.5 if self.frozen else self.speed
            self.x -= speed
    
    def draw(self, surface):
        # 绘制僵尸
        rect = pygame.Rect(self.x, self.y, GRID_SIZE - 20, GRID_SIZE - 10)
        color = (100, 150, 200) if self.frozen else (100, 180, 100)
        pygame.draw.rect(surface, color, rect)
        
        # 绘制眼睛
        pygame.draw.circle(surface, WHITE, (int(self.x + 20), int(self.y + 25)), 8)
        pygame.draw.circle(surface, BLACK, (int(self.x + 20), int(self.y + 25)), 4)
        
        # 血条
        hp_ratio = self.hp / self.max_hp
        pygame.draw.rect(surface, RED, (self.x, self.y - 8, (GRID_SIZE-20) * hp_ratio, 4))
    
    def take_damage(self, damage):
        self.hp -= damage
    
    def is_off_screen(self):
        return self.x < -50

class Conehead(Zombie):
    """路障僵尸"""
    def __init__(self, row):
        super().__init__(row, hp=200)
        self.speed = 0.4

class Buckethead(Zombie):
    """铁桶僵尸"""
    def __init__(self, row):
        super().__init__(row, hp=400)
        self.speed = 0.3

# ========== 阳光类 ==========
class Sun:
    """阳光"""
    def __init__(self, x, y, falling=True):
        self.x = x
        self.y = y
        self.target_y = y
        self.falling = falling
        self.collected = False
        self.size = 40
        
        # 收集后飞向UI
        self.flying = False
        self.target_x = 50
        self.target_y = 50
    
    def update(self):
        if self.falling:
            self.y += 2
            if self.y >= self.target_y:
                self.falling = False
        elif self.flying:
            dx = self.target_x - self.x
            dy = self.target_y - self.y
            self.x += dx * 0.1
            self.y += dy * 0.1
            if abs(dx) < 5 and abs(dy) < 5:
                self.collected = True
    
    def draw(self, surface):
        # 绘制阳光
        color = YELLOW
        center = (int(self.x), int(self.y))
        
        # 光芒
        for i in range(8):
            angle = i * 45
            end_x = self.x + 25 * pygame.math.Vector2(1, 0).rotate(angle).x
            end_y = self.y + 25 * pygame.math.Vector2(1, 0).rotate(angle).y
            pygame.draw.line(surface, color, center, (int(end_x), int(end_y)), 2)
        
        # 中心
        pygame.draw.circle(surface, color, center, 15)
        pygame.draw.circle(surface, (255, 255, 200), center, 10)

# ========== 游戏主类 ==========
class Game:
    def __init__(self):
        self.plants = []
        self.zombies = []
        self.peas = []
        self.suns = []
        self.explosions = []
        
        self.sun_amount = 150
        self.score = 0
        self.game_over = False
        self.wave = 1
        self.zombies_to_spawn = 0
        self.spawn_timer = 0
        
        # 选中植物
        self.selected_plant = None
        
        # 植物卡片
        self.plant_cards = [
            {"type": "peashooter", "cost": 100, "color": GREEN},
            {"type": "sunflower", "cost": 50, "color": YELLOW},
            {"type": "wallnut", "cost": 50, "color": BROWN},
            {"type": "snowpea", "cost": 175, "color": BLUE},
            {"type": "cherrybomb", "cost": 150, "color": RED},
        ]
        self.selected_card = None
        
        # 网格位置映射
        self.grid = [[None for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]
    
    def select_card(self, index):
        """选择植物卡片"""
        if index < len(self.plant_cards):
            card = self.plant_cards[index]
            if self.sun_amount >= card["cost"]:
                self.selected_card = card
    
    def place_plant(self, x, y):
        """放置植物"""
        if not self.selected_card:
            return
        
        # 计算网格位置
        col = x // GRID_SIZE
        row = y // GRID_SIZE
        
        if col >= GRID_COLS or row >= GRID_ROWS:
            return
        
        # 检查位置是否已有植物
        if self.grid[row][col]:
            return
        
        # 创建植物
        plant_type = self.selected_card["type"]
        cost = self.selected_card["cost"]
        
        if plant_type == "peashooter":
            plant = Peashooter(col * GRID_SIZE, row * GRID_SIZE)
        elif plant_type == "sunflower":
            plant = Sunflower(col * GRID_SIZE, row * GRID_SIZE)
        elif plant_type == "wallnut":
            plant = WallNut(col * GRID_SIZE, row * GRID_SIZE)
        elif plant_type == "snowpea":
            plant = SnowPea(col * GRID_SIZE, row * GRID_SIZE)
        elif plant_type == "cherrybomb":
            plant = CherryBomb(col * GRID_SIZE, row * GRID_SIZE)
        else:
            return
        
        self.plants.append(plant)
        self.grid[row][col] = plant
        self.sun_amount -= cost
        self.selected_card = None
    
    def spawn_zombie(self):
        """生成僵尸"""
        if self.zombies_to_spawn > 0:
            row = random.randint(0, GRID_ROWS - 1)
            zombie_type = random.random()
            
            if zombie_type < 0.7:
                zombie = Zombie(row)
            elif zombie_type < 0.9:
                zombie = Conehead(row)
            else:
                zombie = Buckethead(row)
            
            self.zombies.append(zombie)
            self.zombies_to_spawn -= 1
    
    def update(self, current_time):
        """更新游戏状态"""
        if self.game_over:
            return
        
        # 生成波次
        if self.zombies_to_spawn == 0 and len(self.zombies) == 0:
            self.wave += 1
            self.zombies_to_spawn = 3 + self.wave * 2
        
        # 僵尸生成计时
        if self.zombies_to_spawn > 0:
            if current_time - self.spawn_timer > 3000:
                self.spawn_zombie()
                self.spawn_timer = current_time
        
        # 更新植物
        for plant in self.plants:
            if isinstance(plant, (Peashooter, SnowPea)):
                if plant.can_shoot(current_time):
                    # 检查同一行是否有僵尸
                    has_zombie_in_row = any(z.row == plant.y // GRID_SIZE and z.x > plant.x for z in self.zombies)
                    if has_zombie_in_row:
                        pea = plant.shoot(current_time)
                        self.peas.append(pea)
            
            elif isinstance(plant, Sunflower):
                if plant.can_produce(current_time):
                    sun = plant.produce(current_time)
                    self.suns.append(sun)
            
            elif isinstance(plant, CherryBomb):
                # 立即爆炸
                explosion = plant.explode()
                self.explosions.append(explosion)
                
                # 对周围僵尸造成伤害
                for zombie in self.zombies[:]:
                    if abs(zombie.x - plant.x) < 150 and abs(zombie.y - plant.y) < 150:
                        zombie.take_damage(1800)
                
                # 移除植物
                row = plant.y // GRID_SIZE
                col = plant.x // GRID_SIZE
                if self.grid[row][col] == plant:
                    self.grid[row][col] = None
                self.plants.remove(plant)
        
        # 更新子弹
        for pea in self.peas[:]:
            pea.move()
            
            # 检测碰撞
            for zombie in self.zombies:
                if (abs(pea.x - zombie.x) < 30 and 
                    abs(pea.y - zombie.y - GRID_SIZE//2 + 10) < 30):
                    zombie.take_damage(pea.damage)
                    if pea in self.peas:
                        self.peas.remove(pea)
                    break
            
            if pea.is_off_screen():
                if pea in self.peas:
                    self.peas.remove(pea)
        
        # 更新僵尸
        for zombie in self.zombies[:]:
            # 检查是否被爆炸杀死
            for explosion in self.explosions:
                if abs(zombie.x - explosion.x) < explosion.radius:
                    zombie.take_damage(explosion.damage)
            
            if zombie.hp <= 0:
                self.zombies.remove(zombie)
                self.score += 10
                continue
            
            # 移动
            zombie.move()
            
            # 解冻
            if zombie.frozen:
                if current_time - zombie.frozen_timer > 5000:
                    zombie.frozen = False
            
            # 检查是否吃植物
            zombie.eating = False
            for plant in self.plants:
                if (abs(zombie.x - plant.x - GRID_SIZE//2) < 30 and 
                    abs(zombie.y - plant.y) < 10):
                    zombie.eating = True
                    plant.hp -= zombie.damage
                    
                    if plant.hp <= 0:
                        # 移除植物
                        row = plant.y // GRID_SIZE
                        col = plant.x // GRID_SIZE
                        if self.grid[row][col] == plant:
                            self.grid[row][col] = None
                        self.plants.remove(plant)
            
            # 检查是否到达左侧
            if zombie.is_off_screen():
                self.game_over = True
        
        # 更新阳光
        for sun in self.suns[:]:
            sun.update()
            if sun.collected:
                self.suns.remove(sun)
        
        # 更新爆炸
        for explosion in self.explosions[:]:
            explosion.update()
            if explosion.done:
                self.explosions.remove(explosion)
    
    def draw(self, surface):
        """绘制游戏"""
        # 背景
        surface.fill((50, 150, 50))
        
        # 绘制草地网格
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                rect = pygame.Rect(col * GRID_SIZE, row * GRID_SIZE, GRID_SIZE, GRID_SIZE)
                pygame.draw.rect(surface, (60, 160, 60), rect, 1)
        
        # 绘制植物
        for plant in self.plants:
            plant.draw(surface)
        
        # 绘制僵尸
        for zombie in self.zombies:
            zombie.draw(surface)
        
        # 绘制子弹
        for pea in self.peas:
            pea.draw(surface)
        
        # 绘制阳光
        for sun in self.suns:
            sun.draw(surface)
        
        # 绘制爆炸
        for explosion in self.explosions:
            explosion.draw(surface)
        
        # 绘制UI
        self.draw_ui(surface)
    
    def draw_ui(self, surface):
        """绘制UI"""
        # 顶部栏背景
        pygame.draw.rect(surface, (80, 80, 80), (0, 0, SCREEN_WIDTH, 80))
        
        # 阳光数量
        font = pygame.font.Font(None, 36)
        text = font.render(f"☀ {self.sun_amount}", True, YELLOW)
        surface.blit(text, (10, 25))
        
        # 分数
        text = font.render(f"分数: {self.score}", True, WHITE)
        surface.blit(text, (150, 25))
        
        # 波次
        text = font.render(f"波次: {self.wave}", True, WHITE)
        surface.blit(text, (300, 25))
        
        # 植物卡片
        card_width = 70
        card_height = 60
        card_x = 450
        
        for i, card in enumerate(self.plant_cards):
            rect = pygame.Rect(card_x + i * (card_width + 10), 10, card_width, card_height)
            
            # 选中状态
            if self.selected_card == card:
                pygame.draw.rect(surface, (255, 255, 0), rect, 3)
            else:
                pygame.draw.rect(surface, GRAY, rect, 2)
            
            # 卡片背景
            pygame.draw.rect(surface, card["color"], (rect.x + 5, rect.y + 5, card_width - 10, card_height - 25))
            
            # 费用
            cost_text = font.render(str(card["cost"]), True, YELLOW)
            surface.blit(cost_text, (rect.x + 20, rect.y + 45))
            
            # 快捷键提示
            key_text = font.render(str(i+1), True, WHITE)
            surface.blit(key_text, (rect.x + 5, rect.y - 5))
        
        # 游戏结束
        if self.game_over:
            font = pygame.font.Font(None, 72)
            text = font.render("GAME OVER", True, RED)
            text_rect = text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
            pygame.draw.rect(surface, BLACK, text_rect.inflate(20, 20))
            surface.blit(text, text_rect)
    
    def handle_click(self, x, y):
        """处理点击"""
        # 点击卡片区域
        if y < 80:
            if x > 450:
                index = (x - 450) // 80
                self.select_card(index)
            return
        
        # 点击放置植物
        if self.selected_card:
            self.place_plant(x, y)
    
    def handle_sun_click(self, x, y):
        """点击收集阳光"""
        for sun in self.suns:
            if not sun.flying and not sun.falling:
                if abs(x - sun.x) < 30 and abs(y - sun.y) < 30:
                    sun.flying = True
                    self.sun_amount += 25
                    return

# ========== 主循环 ==========
def main():
    game = Game()
    
    running = True
    while running:
        current_time = pygame.time.get_ticks()
        
        # 事件处理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                x, y = pygame.mouse.get_pos()
                
                # 左键点击
                if event.button == 1:
                    # 先检查阳光
                    game.handle_sun_click(x, y)
                    # 再检查其他
                    game.handle_click(x, y)
                
                # 右键取消选择
                elif event.button == 3:
                    game.selected_card = None
            
            elif event.type == pygame.KEYDOWN:
                # 数字键选择植物
                if event.key == pygame.K_1:
                    game.select_card(0)
                elif event.key == pygame.K_2:
                    game.select_card(1)
                elif event.key == pygame.K_3:
                    game.select_card(2)
                elif event.key == pygame.K_4:
                    game.select_card(3)
                elif event.key == pygame.K_5:
                    game.select_card(4)
                elif event.key == pygame.K_ESCAPE:
                    game.selected_card = None
        
        # 更新
        game.update(current_time)
        
        # 绘制
        game.draw(screen)
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
