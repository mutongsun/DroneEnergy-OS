<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { createDrone, deleteDrone, listDrones, updateDrone } from '@/api/drones'
import { useAuthStore } from '@/stores/auth'
import type { Drone, DroneStatus } from '@/types/api'

const auth = useAuthStore()

// ---------- 列表 + 筛选 + 分页 ----------
const rows = ref<Drone[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({
  status: '' as string,
  model: '',
  page: 1,
  page_size: 10,
})

const statusOptions: { label: string; value: DroneStatus }[] = [
  { label: '空闲', value: 'idle' },
  { label: '飞行中', value: 'flying' },
  { label: '维护中', value: 'maintenance' },
  { label: '离线', value: 'offline' },
]

const statusLabel = computed(
  () => new Map(statusOptions.map((o) => [o.value as string, o.label])),
)

const statusTagType: Record<DroneStatus, 'info' | 'success' | 'warning' | 'danger'> = {
  idle: 'info',
  flying: 'success',
  maintenance: 'warning',
  offline: 'danger',
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await listDrones({
      status: query.status || undefined,
      model: query.model || undefined,
      page: query.page,
      page_size: query.page_size,
    })
    rows.value = page.items
    total.value = page.total
  } catch {
    ElMessage.error('设备列表加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch(): void {
  query.page = 1
  void load()
}

onMounted(load)

// ---------- 新建 / 编辑 ----------
const dialogVisible = ref(false)
const editingId = ref<number | null>(null) // null = 新建
const form = reactive({
  name: '',
  model: '',
  status: 'idle' as DroneStatus,
  max_battery_mah: 5000,
})

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { name: '', model: '', status: 'idle', max_battery_mah: 5000 })
  dialogVisible.value = true
}

function openEdit(row: Drone): void {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    model: row.model,
    status: row.status,
    max_battery_mah: row.max_battery_mah,
  })
  dialogVisible.value = true
}

async function onSave(): Promise<void> {
  try {
    if (editingId.value === null) {
      await createDrone({ ...form })
      ElMessage.success('创建成功')
    } else {
      await updateDrone(editingId.value, { ...form })
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    await load()
  } catch (err) {
    const detail = err instanceof Error ? err.message : '请求失败'
    ElMessage.error(`保存失败：${detail}`)
  }
}

async function onDelete(row: Drone): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除设备「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return // 用户取消
  }
  try {
    await deleteDrone(row.id)
    ElMessage.success('删除成功')
    await load()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select
        v-model="query.status"
        clearable
        placeholder="状态筛选"
        class="filter"
        @change="onSearch"
      >
        <el-option
          v-for="o in statusOptions"
          :key="o.value"
          :label="o.label"
          :value="o.value"
        />
      </el-select>
      <el-input
        v-model="query.model"
        clearable
        placeholder="机型筛选"
        class="filter"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-button @click="onSearch">
        查询
      </el-button>
      <el-button
        v-if="auth.canWrite"
        type="primary"
        :icon="Plus"
        @click="openCreate"
      >
        新建设备
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="rows"
      stripe
    >
      <el-table-column
        prop="id"
        label="ID"
        width="70"
      />
      <el-table-column
        prop="name"
        label="名称"
        min-width="140"
      />
      <el-table-column
        prop="model"
        label="机型"
        min-width="120"
      />
      <el-table-column
        label="状态"
        width="110"
      >
        <template #default="{ row }">
          <el-tag :type="statusTagType[row.status as DroneStatus]">
            {{ statusLabel.get(row.status) ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="max_battery_mah"
        label="电池容量 (mAh)"
        width="150"
      />
      <el-table-column
        prop="created_at"
        label="创建时间"
        min-width="170"
      />
      <el-table-column
        v-if="auth.canWrite"
        label="操作"
        width="160"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            size="small"
            @click="openEdit(row)"
          >
            编辑
          </el-button>
          <el-button
            size="small"
            type="danger"
            @click="onDelete(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.page_size"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next"
      class="pager"
      @current-change="load"
      @size-change="onSearch"
    />

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新建设备' : '编辑设备'"
      width="480px"
    >
      <el-form
        :model="form"
        label-width="100px"
      >
        <el-form-item
          label="名称"
          required
        >
          <el-input
            v-model="form.name"
            maxlength="100"
          />
        </el-form-item>
        <el-form-item
          label="机型"
          required
        >
          <el-input
            v-model="form.model"
            maxlength="50"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status">
            <el-option
              v-for="o in statusOptions"
              :key="o.value"
              :label="o.label"
              :value="o.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="电池容量">
          <el-input-number
            v-model="form.max_battery_mah"
            :min="1"
            :max="100000"
            :step="500"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="onSave"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.filter {
  width: 180px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
