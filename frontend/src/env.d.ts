/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

// 样式文件的副作用导入声明：避免在未安装 vite 类型时类型检查失败。
declare module '*.css'
declare module '*.scss'
