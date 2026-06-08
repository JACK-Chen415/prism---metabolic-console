import React from 'react';
import { View } from '../../types';

interface PackagedFoodScanViewProps {
  onViewChange: (view: View) => void;
}

const PackagedFoodScanView: React.FC<PackagedFoodScanViewProps> = ({ onViewChange }) => {
  return (
    <div className="flex min-h-[calc(100vh-88px)] flex-col px-4 pb-8 pt-4">
      <div className="rounded-2xl border border-white/5 bg-surface-dark p-5 shadow-lg">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold tracking-[0.28em] text-primary/80">PACKAGED FOOD</p>
            <h1 className="mt-2 text-2xl font-bold tracking-wide text-white font-serif">包装食品扫描</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400 font-serif">
              这里是条码优先的 OCR / 扫描入口。当前先提供安全占位页，后续可接入摄像头扫码、OCR 识别和标签归一化。
            </p>
          </div>
          <span className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[10px] font-bold tracking-wide text-primary">
            TODO-safe
          </span>
        </div>

        <div className="mt-5 rounded-2xl border border-dashed border-primary/20 bg-black/20 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <span className="material-symbols-outlined icon-filled text-2xl">barcode_scanner</span>
            </div>
            <div>
              <p className="text-sm font-bold text-white font-serif">条码优先，OCR 兜底</p>
              <p className="mt-1 text-xs leading-5 text-slate-500 font-serif">
                入口已预留，可在此触发摄像头识别、相册导入或手动录入包装食品标签。
              </p>
            </div>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => onViewChange(View.CAMERA)}
              className="h-12 rounded-xl border border-primary/20 bg-primary/15 text-sm font-bold tracking-wide text-primary transition-colors hover:bg-primary/20"
            >
              去相机识别
            </button>
            <button
              type="button"
              onClick={() => onViewChange(View.LOG)}
              className="h-12 rounded-xl border border-white/10 bg-white/5 text-sm font-bold tracking-wide text-slate-200 transition-colors hover:bg-white/10"
            >
              打开日志中的包装食品区
            </button>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-amber-300/15 bg-amber-500/10 p-4 text-sm leading-6 text-amber-100 font-serif">
          当前页面不执行真实 OCR 或条码推断，只作为清晰入口与后续 API 对接点，避免影响现有日志 / 聊天流程。
        </div>
      </div>
    </div>
  );
};

export default PackagedFoodScanView;