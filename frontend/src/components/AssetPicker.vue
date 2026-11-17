<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

export interface AssetOption {
  id: string
  name: string
  docket_no?: string | null
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    assets?: AssetOption[]
    placeholder?: string
    search?: (query: string) => Promise<AssetOption[]>
  }>(),
  { assets: () => [], placeholder: '输入案件名称或我方文号搜索' },
)

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()

const open = ref(false)
const query = ref('')
const activeIndex = ref(0)
const inputEl = ref<HTMLInputElement | null>(null)
const listEl = ref<HTMLDivElement | null>(null)
const rootEl = ref<HTMLElement | null>(null)
const remoteItems = ref<AssetOption[]>([])
const searching = ref(false)
let searchGeneration = 0
let searchTimer: ReturnType<typeof setTimeout> | null = null

const selected = computed(() => {
  const pool = [...props.assets, ...remoteItems.value]
  return pool.find((asset) => asset.id === props.modelValue) ?? null
})

const localMatches = computed(() => {
  const text = query.value.trim().toLowerCase()
  if (!text) return props.assets.slice(0, 50)
  const scored = props.assets
    .map((asset) => {
      const haystack = `${asset.name} ${asset.docket_no ?? ''}`.toLowerCase()
      if (!haystack.includes(text)) return null
      const starts = asset.name.toLowerCase().startsWith(text) || (asset.docket_no ?? '').toLowerCase().startsWith(text)
      return { asset, score: starts ? 0 : 1 }
    })
    .filter((item): item is { asset: AssetOption; score: number } => item !== null)
  scored.sort((a, b) => a.score - b.score)
  return scored.slice(0, 50).map((item) => item.asset)
})

const matches = computed(() => (props.search ? remoteItems.value : localMatches.value))
const listboxId = `asset-picker-${Math.random().toString(36).slice(2)}`
const activeOptionId = computed(() => (matches.value[activeIndex.value] ? `${listboxId}-${activeIndex.value}` : undefined))

async function runSearch(text: string) {
  if (!props.search) return
  const generation = ++searchGeneration
  searching.value = true
  try {
    const result = await props.search(text.trim())
    if (generation === searchGeneration) remoteItems.value = result
  } catch {
    if (generation === searchGeneration) remoteItems.value = []
  } finally {
    if (generation === searchGeneration) searching.value = false
  }
}

watch(query, (value) => {
  activeIndex.value = 0
  if (!props.search || !open.value) return
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void runSearch(value), 250)
})

function openList() {
  open.value = true
  query.value = ''
  activeIndex.value = 0
  if (props.search) void runSearch('')
  void nextTick(() => inputEl.value?.focus())
}

function closeList() {
  open.value = false
  query.value = ''
  searchGeneration += 1
}

function onDocumentPointerDown(event: MouseEvent) {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target as Node)) closeList()
}

watch(open, (value) => {
  if (value) document.addEventListener('mousedown', onDocumentPointerDown)
  else document.removeEventListener('mousedown', onDocumentPointerDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocumentPointerDown)
  if (searchTimer) clearTimeout(searchTimer)
  searchGeneration += 1
})

function choose(asset: AssetOption) {
  remoteItems.value = [asset, ...remoteItems.value.filter((item) => item.id !== asset.id)]
  emit('update:modelValue', asset.id)
  closeList()
}

function clearSelection(event: Event) {
  event.stopPropagation()
  emit('update:modelValue', '')
  openList()
}

function move(delta: number) {
  if (!open.value) return openList()
  const total = matches.value.length
  if (!total) return
  activeIndex.value = (activeIndex.value + delta + total) % total
  const node = listEl.value?.children[activeIndex.value] as HTMLElement | undefined
  node?.scrollIntoView({ block: 'nearest' })
}

function confirmActive() {
  const asset = matches.value[activeIndex.value]
  if (asset) choose(asset)
}

watch(matches, () => { activeIndex.value = 0 })
</script>

<template>
  <div ref="rootEl" class="asset-picker" @keydown.esc="closeList">
    <button v-if="selected && !open" type="button" class="picker-selected" @click="openList">
      <span class="picker-name">{{ selected.name }}</span>
      <span v-if="selected.docket_no" class="picker-docket">{{ selected.docket_no }}</span>
      <span class="picker-clear" aria-label="清除选择" role="button" tabindex="0" @click="clearSelection" @keydown.enter.prevent="clearSelection">×</span>
    </button>

    <template v-else>
      <input
        ref="inputEl"
        v-model="query"
        class="field picker-input"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="open"
        :aria-controls="listboxId"
        :aria-activedescendant="activeOptionId"
        :aria-busy="searching"
        :placeholder="placeholder"
        @focus="openList"
        @click="open = true"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
        @keydown.enter.prevent="confirmActive()"
        @keydown.esc.prevent="closeList()"
      />

      <div v-if="open" :id="listboxId" ref="listEl" class="picker-list" role="listbox">
        <button
          v-for="(asset, index) in matches"
          :id="`${listboxId}-${index}`"
          :key="asset.id"
          type="button"
          role="option"
          :aria-selected="index === activeIndex"
          class="picker-option"
          :class="{ active: index === activeIndex }"
          @mousedown.prevent="choose(asset)"
          @mouseenter="activeIndex = index"
        >
          <span class="picker-name">{{ asset.name }}</span>
          <span v-if="asset.docket_no" class="picker-docket">{{ asset.docket_no }}</span>
        </button>
        <p v-if="searching" class="picker-empty" role="status">搜索中…</p>
        <p v-else-if="matches.length === 0" class="picker-empty" role="status">没有匹配的案件</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.asset-picker { position: relative; min-width: 320px; }
.picker-input { width: 100%; }
.picker-selected { width: 100%; display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; cursor: pointer; text-align: left; }
.picker-selected:hover { border-color: #9fbdf8; }
.picker-name { font-size: 13px; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.picker-selected .picker-name { flex: 1; }
.picker-docket { font-size: 11px; color: var(--muted); white-space: nowrap; }
.picker-clear { color: var(--muted); font-size: 16px; line-height: 1; padding: 0 2px; }
.picker-clear:hover { color: var(--red); }
.picker-list { position: absolute; z-index: 40; top: calc(100% + 4px); left: 0; right: 0; max-height: 260px; overflow: auto; background: #fff; border: 1px solid var(--line); border-radius: 9px; box-shadow: 0 12px 30px rgba(28, 50, 85, .14); padding: 4px; }
.picker-option { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border: 0; border-radius: 7px; background: transparent; text-align: left; cursor: pointer; }
.picker-option.active, .picker-option:hover { background: #eef4ff; }
.picker-empty { margin: 0; padding: 12px; font-size: 12px; color: var(--muted); text-align: center; }
</style>
