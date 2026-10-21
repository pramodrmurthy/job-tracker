// jsdom lacks ResizeObserver (recharts) and <dialog>.showModal/close.
class RO { observe() {} unobserve() {} disconnect() {} }
;(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO
HTMLDialogElement.prototype.showModal ||= function (this: HTMLDialogElement) { this.setAttribute('open', '') }
HTMLDialogElement.prototype.close ||= function (this: HTMLDialogElement) { this.removeAttribute('open') }
URL.createObjectURL ||= () => 'blob:mock'
URL.revokeObjectURL ||= () => {}
