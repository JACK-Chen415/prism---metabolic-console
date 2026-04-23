import React from 'react';
import { View } from '../../types';

interface HealthReportArchivesViewProps {
  onViewChange: (view: View) => void;
}

const HealthReportArchivesView: React.FC<HealthReportArchivesViewProps> = ({ onViewChange }) => {
  return (
    <div className="flex flex-col w-full h-full bg-[#080c0d] animate-fade-in">
      <div className="sticky top-0 z-20 bg-[#080c0d]/95 backdrop-blur-md border-b border-white/5">
        <div className="flex items-center gap-4 p-4">
          <button
            onClick={() => onViewChange(View.PROFILE)}
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors -ml-2"
          >
            <span className="material-symbols-outlined text-white/80">arrow_back</span>
          </button>
          <h1 className="text-white text-xl font-bold font-serif tracking-widest">体检档案</h1>
        </div>
      </div>

      <div className="flex-1 p-6 pb-24">
        <div className="rounded-2xl border border-white/10 bg-[#131b1d] p-6">
          <div className="w-14 h-14 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-4">
            <span className="material-symbols-outlined text-primary text-3xl">description</span>
          </div>
          <h2 className="text-white text-lg font-bold font-serif mb-2">体检原始档案暂未接入</h2>
          <p className="text-slate-400 text-sm leading-relaxed font-serif">
            当前版本已关闭示例体检数据和本地伪造报告，避免误导。后续接入真实档案与报告接口后，这里会展示可追溯的分析结果。
          </p>
        </div>

        <button
          onClick={() => onViewChange(View.CHAT)}
          className="mt-6 w-full py-3 rounded-xl bg-white/10 text-slate-300 font-bold border border-white/10 hover:bg-white/15 transition-all"
        >
          去 AI 咨询真实记录
        </button>
      </div>
    </div>
  );
};

export default HealthReportArchivesView;
