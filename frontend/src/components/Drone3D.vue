<script setup lang="ts">
import { onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import * as THREE from 'three'
import type { SensorFrame } from '@/types/api'

/**
 * 无人机 3D 姿态可视化：
 * - 机体：十字机架 + 4 旋翼（俯视视角辨识度最高）
 * - pitch/yaw/roll 驱动机体欧拉角，altitude 驱动垂直位置
 * - 旋翼转速随电流（负载）变化，模拟真实感
 * - 机头方向可视化：顶部前向箭头 + 橙色前电机 + 红色机头灯
 *   （X 型机架四重对称，不做标记则 yaw 旋转肉眼不可辨）
 * - 左上角 HUD 实时读数：姿态数值与画面互相印证
 */

const props = defineProps<{ frame: SensorFrame | null }>()

const container = shallowRef<HTMLDivElement | null>(null)
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let drone: THREE.Group
let rotors: THREE.Mesh[] = []
let rafId = 0
// 相机注视点高度：向机体高度平滑追踪，高高度飞行时机体不飞出画面
let camTargetY = 2

function buildScene(): void {
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0f172a)
  scene.fog = new THREE.Fog(0x0f172a, 30, 80)

  camera = new THREE.PerspectiveCamera(50, 1, 0.1, 200)
  camera.position.set(10, 8, 12)
  camera.lookAt(0, 2, 0)

  // 灯光：环境光 + 主方向光 + 补光
  scene.add(new THREE.AmbientLight(0xffffff, 0.5))
  const key = new THREE.DirectionalLight(0xffffff, 1.2)
  key.position.set(8, 15, 10)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0x38bdf8, 0.4)
  rim.position.set(-10, 6, -8)
  scene.add(rim)

  // 地面网格：高度参照系
  const grid = new THREE.GridHelper(60, 30, 0x334155, 0x1e293b)
  scene.add(grid)

  drone = buildDrone()
  scene.add(drone)
}

function buildDrone(): THREE.Group {
  const group = new THREE.Group()
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.6, roughness: 0.3 })
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.4, roughness: 0.4 })
  // 前向标记材质：橙色仅用于机头方向元素，打破 X 机架四重对称
  const noseMat = new THREE.MeshStandardMaterial({ color: 0xf97316, emissive: 0xf97316, emissiveIntensity: 0.6 })

  // 中心机身
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.5, 1.6), bodyMat)
  group.add(body)

  // 电池块（顶面凸起，视觉重心）
  const battery = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.3, 0.8), accentMat)
  battery.position.y = 0.4
  group.add(battery)

  // 四臂 + 旋翼
  const armMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.7, roughness: 0.3 })
  const armLen = 1.6
  const positions: Array<[number, number]> = [
    [armLen, armLen],
    [-armLen, armLen],
    [armLen, -armLen],
    [-armLen, -armLen],
  ]
  for (const [x, z] of positions) {
    const arm = new THREE.Mesh(new THREE.BoxGeometry(armLen * 1.5, 0.12, 0.2), armMat)
    arm.position.set(x / 2, 0, z / 2)
    arm.rotation.y = Math.atan2(z, x)
    group.add(arm)

    // 前电机橙色、后电机银灰：与顶部箭头共同指示机头朝向
    const motor = new THREE.Mesh(
      new THREE.CylinderGeometry(0.22, 0.26, 0.25, 12),
      z > 0 ? noseMat : bodyMat,
    )
    motor.position.set(x, 0.15, z)
    group.add(motor)

    // 旋翼：两片桨叶的薄盒，绕 Y 轴自转
    const rotor = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.03, 0.12), accentMat)
    rotor.position.set(x, 0.32, z)
    group.add(rotor)
    rotors.push(rotor)
  }

  // 顶部前向箭头（俯视视角下 yaw 的主要判据）
  const arrow = new THREE.Mesh(new THREE.ConeGeometry(0.13, 0.55, 10), noseMat)
  arrow.rotation.x = Math.PI / 2 // 默认朝 +Y，转 90° 后指向机头方向 +Z
  arrow.position.set(0, 0.62, 0.55)
  group.add(arrow)

  // 前向指示灯（区分机头朝向）
  const nose = new THREE.Mesh(
    new THREE.SphereGeometry(0.14, 10, 10),
    new THREE.MeshStandardMaterial({ color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 1 }),
  )
  nose.position.set(0, 0, 1.0)
  group.add(nose)

  return group
}

/** 最短路径角度插值：yaw 跨 ±180° 边界时避免绕远路旋转近 360° */
function angleLerp(current: number, target: number, t: number): number {
  const TWO_PI = Math.PI * 2
  let delta = (target - current) % TWO_PI
  if (delta > Math.PI) delta -= TWO_PI
  if (delta < -Math.PI) delta += TWO_PI
  return current + delta * t
}

/** 传感器帧 → 机体姿态/位置（带缓动，避免 1Hz 帧间跳变） */
function applyFrame(frame: SensorFrame): void {
  // 目标欧拉角：绕 X 前倾(pitch)、绕 Y 航向(yaw)、绕 Z 侧倾(roll)
  const targetPitch = THREE.MathUtils.degToRad(frame.pitch_deg)
  const targetYaw = THREE.MathUtils.degToRad(frame.yaw_deg)
  const targetRoll = THREE.MathUtils.degToRad(frame.roll_deg)
  const targetAlt = frame.altitude_m / 10 // 100m 映射到 10 单位，同屏可见

  const lerp = 0.15 // 缓动系数
  drone.rotation.x = angleLerp(drone.rotation.x, targetPitch, lerp)
  drone.rotation.y = angleLerp(drone.rotation.y, targetYaw, lerp)
  drone.rotation.z = angleLerp(drone.rotation.z, targetRoll, lerp)
  drone.position.y += (1 + targetAlt - drone.position.y) * lerp

  // 相机垂直追踪机体高度：高空飞行时机体保持在画面内，网格提供高度参照
  camTargetY += (drone.position.y - camTargetY) * lerp
  camera.lookAt(0, camTargetY, 0)
}

/** 动画循环：旋翼自转（转速随电流） + 缓动逼近目标姿态 */
function animate(): void {
  const current = props.frame
  const speed = current ? 0.3 + current.current_a / 20 : 0.3
  for (const rotor of rotors) {
    rotor.rotation.y += speed
  }
  if (current !== null) {
    applyFrame(current)
  }
  renderer?.render(scene, camera)
  rafId = requestAnimationFrame(animate)
}

function onResize(): void {
  if (container.value === null || renderer === null) return
  const w = container.value.clientWidth
  const h = container.value.clientHeight
  renderer.setSize(w, h)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
}

onMounted(() => {
  if (container.value === null) return
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  container.value.appendChild(renderer.domElement)
  buildScene()
  onResize()
  window.addEventListener('resize', onResize)
  animate()
})

watch(
  () => props.frame,
  (f) => {
    if (f !== null) applyFrame(f)
  },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(rafId)
  window.removeEventListener('resize', onResize)
  renderer?.dispose()
  renderer = null
  rotors = []
})
</script>

<template>
  <div
    ref="container"
    class="drone3d"
  >
    <!-- 姿态 HUD：数值读数与 3D 画面互相印证，联动一目了然 -->
    <div
      v-if="frame"
      class="hud"
    >
      <span>PITCH {{ frame.pitch_deg.toFixed(1) }}°</span>
      <span>YAW {{ frame.yaw_deg.toFixed(1) }}°</span>
      <span>ROLL {{ frame.roll_deg.toFixed(1) }}°</span>
      <span>ALT {{ frame.altitude_m.toFixed(1) }}m</span>
    </div>
  </div>
</template>

<style scoped>
.drone3d {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
}

.hud {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 1;
  display: flex;
  gap: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.72);
  color: #7dd3fc;
  font-family: ui-monospace, 'Cascadia Mono', 'Courier New', monospace;
  font-size: 12px;
  pointer-events: none;
}
</style>
