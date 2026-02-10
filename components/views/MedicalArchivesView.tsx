import React, { useState } from 'react';
import { View, ConditionData, ConditionStatus, TrendType } from '../../types';
import { ConditionsAPI, TokenManager } from '../../services/api';

interface MedicalArchivesViewProps {
  onViewChange: (view: View) => void;
  conditions: ConditionData[];
  setConditions: React.Dispatch<React.SetStateAction<ConditionData[]>>;
}

const MedicalArchivesView: React.FC<MedicalArchivesViewProps> = ({ onViewChange, conditions, setConditions }) => {
  // Local UI state
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  // Modal State
  const [showModal, setShowModal] = useState(false);
  const [editingItem, setEditingItem] = useState<Partial<ConditionData>>({});

  // Delete Confirmation State
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const handleSave = async () => {
    if (!editingItem.title) return;

    if (editingItem.id) {
      // 编辑已有档案（乐观更新）
      setConditions(prev => prev.map(c => c.id === editingItem.id ? { ...c, ...editingItem } as ConditionData : c));

      // 同步后端
      if (TokenManager.isAuthenticated()) {
        try {
          const numId = parseInt(editingItem.id);
          if (!isNaN(numId)) {
            await ConditionsAPI.update(numId, {
              status: editingItem.status,
              trend: editingItem.trend,
              value: editingItem.value,
              unit: editingItem.unit,
              dictum: editingItem.dictum,
              attribution: editingItem.attribution
            });
          }
        } catch (error) {
          console.error('更新健康档案失败:', error);
        }
      }
    } else {
      // 新增档案
      const newItem: ConditionData = {
        id: Date.now().toString(),
        title: editingItem.title || '未命名',
        icon: editingItem.type === 'ALLERGY' ? 'warning' : 'monitor_heart',
        status: editingItem.status || 'STABLE',
        trend: 'STABLE',
        dictum: '新录入档案，正在建立基准。',
        attribution: '系统正在收集更多数据以生成归因分析。',
        type: editingItem.type || 'CHRONIC',
        value: editingItem.value,
        unit: editingItem.unit,
        ...editingItem
      } as ConditionData;
      setConditions(prev => [newItem, ...prev]);

      // 同步后端
      if (TokenManager.isAuthenticated()) {
        try {
          const result = await ConditionsAPI.create({
            condition_code: newItem.id,
            title: newItem.title,
            icon: newItem.icon,
            condition_type: (newItem.type || 'CHRONIC') as 'CHRONIC' | 'ALLERGY',
            status: newItem.status as 'ACTIVE' | 'MONITORING' | 'STABLE' | 'ALERT',
            value: newItem.value,
            unit: newItem.unit
          }) as any;
          // 用后端返回的真ID替换临时ID
          if (result?.id) {
            setConditions(prev => prev.map(c =>
              c.id === newItem.id ? { ...c, id: String(result.id) } : c
            ));
          }
        } catch (error) {
          console.error('创建健康档案失败:', error);
        }
      }
    }
    setShowModal(false);
    setEditingItem({});
  };

  const confirmDelete = async () => {
    if (deleteId) {
      setConditions(prev => prev.filter(c => c.id !== deleteId));

      // 同步后端
      if (TokenManager.isAuthenticated()) {
        try {
          const numId = parseInt(deleteId);
          if (!isNaN(numId)) {
            await ConditionsAPI.delete(numId);
          }
        } catch (error) {
          console.error('删除健康档案失败:', error);
        }
      }

      setDeleteId(null);
    }
  };

  const handleDeleteClick = (id: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Critical: Stop event from bubbling to the card's onClick
    setDeleteId(id);
  };

  const openAddModal = () => {
    setEditingItem({
      type: 'CHRONIC',
      status: 'STABLE',
      icon: 'healing'
    });
    setShowModal(true);
  };

  const openEditModal = (item: ConditionData, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingItem({ ...item });
    setShowModal(true);
  };

  const getStatusColor = (status: ConditionStatus) => {
    switch (status) {
      case 'ACTIVE':
      case 'ALERT':
        return 'text-ochre';
      case 'MONITORING':
      case 'STABLE':
        return 'text-[#45b7aa]';
      default:
        return 'text-white';
    }
  };

  const getStatusBg = (status: ConditionStatus) => {
    switch (status) {
      case 'ACTIVE':
      case 'ALERT':
        return 'bg-ochre/10 border-ochre/30 shadow-[0_0_15px_rgba(217,164,65,0.2)]';
      case 'MONITORING':
      case 'STABLE':
        return 'bg-[#45b7aa]/10 border-[#45b7aa]/30 shadow-[0_0_15px_rgba(69,183,170,0.2)]';
      default:
        return 'bg-white/10 border-white/20';
    }
  };

  const getStatusLabel = (status: ConditionStatus) => {
    switch (status) {
      case 'ACTIVE': return '活跃';
      case 'MONITORING': return '监测中';
      case 'STABLE': return '平稳';
      case 'ALERT': return '过敏';
      default: return '未知';
    }
  };

  const renderTrendPath = (trend: TrendType, color: string) => {
    const width = 140;
    const height = 40;
    let path = '';

    if (trend === 'STABLE') {
      path = `M0,${height / 2} Q${width / 4},${height / 2 - 5} ${width / 2},${height / 2} T${width},${height / 2}`;
    } else if (trend === 'WORSENING') {
      path = `M0,${height} L${width * 0.2},${height * 0.4} L${width * 0.4},${height * 0.8} L${width * 0.6},${height * 0.2} L${width * 0.8},${height * 0.6} L${width},${height * 0.3}`;
    } else {
      path = `M0,${height} C${width * 0.3},${height} ${width * 0.6},${height * 0.8} ${width},0`;
    }

    return (
      <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="opacity-60">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className={color} />
        <path d={`${path} L${width},${height} L0,${height} Z`} fill="currentColor" className={`${color} opacity-5`} />
      </svg>
    );
  };

  return (
    <div className="flex flex-col w-full min-h-screen pb-28 bg-background-dark">
      {/* Header Area */}
      <div className="relative pt-6 pb-6 bg-[#080c0d] px-6">
        <div className="relative flex items-start justify-between">
          <div className="flex flex-col">
            <div className="flex items-center gap-2 mb-1">
              <button
                onClick={() => onViewChange(View.PROFILE)}
                className="w-8 h-8 -ml-2 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors"
              >
                <span className="material-symbols-outlined text-white/80">arrow_back</span>
              </button>
              <h1 className="text-white text-2xl font-bold font-serif tracking-widest">病史背景</h1>
            </div>
            <span className="text-white/40 text-[10px] font-display tracking-[0.4em] uppercase ml-1">Medical Background</span>
            <p className="text-[#45b7aa] text-xs font-serif mt-3 tracking-wider">当前代谢平衡度：四时安泰（平稳）</p>
          </div>

          {/* Edit Button (Toggle) */}
          <button
            onClick={() => setIsEditing(!isEditing)}
            className={`w-16 h-9 flex items-center justify-center rounded-md font-bold text-sm transition-all duration-300 shadow-lg mt-1 ${isEditing
              ? 'bg-primary text-background-dark shadow-[0_0_15px_rgba(17,196,212,0.4)]'
              : 'bg-white/10 text-white hover:bg-white/20'
              }`}
          >
            {isEditing ? '完成' : '编辑'}
          </button>
        </div>
      </div>

      {/* Grid Content */}
      <div className="flex-1 px-4 pb-4">
        <div className="grid grid-cols-1 gap-4">

          {/* Add Button (Only visible in Edit Mode) */}
          {isEditing && (
            <div
              onClick={openAddModal}
              className="h-28 border border-dashed border-white/20 rounded-2xl flex flex-col items-center justify-center bg-white/5 hover:bg-white/10 transition-colors cursor-pointer group active:scale-[0.99] gap-2"
            >
              <span className="material-symbols-outlined text-3xl text-white/40 group-hover:text-primary transition-colors">add_circle</span>
              <span className="font-serif font-bold tracking-wider text-white/40 group-hover:text-white transition-colors text-sm">新增病史档案</span>
            </div>
          )}

          {/* Empty State */}
          {conditions.length === 0 && !isEditing && (
            <div className="flex flex-col items-center justify-center py-24 opacity-40 animate-fade-in">
              <div className="w-24 h-24 rounded-full bg-white/5 flex items-center justify-center mb-4 border border-white/5">
                <span className="material-symbols-outlined text-4xl text-slate-500">content_paste_off</span>
              </div>
              <p className="text-slate-400 font-serif text-sm tracking-widest">暂无病史档案</p>
              <p className="text-slate-600 text-xs mt-2">No medical records found</p>
              <button
                onClick={() => setIsEditing(true)}
                className="mt-8 px-6 py-2.5 rounded-full bg-white/5 border border-white/10 text-white/60 text-xs hover:bg-white/10 transition-colors flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-sm">edit</span>
                添加记录
              </button>
            </div>
          )}

          {conditions.map((item) => {
            const isExpanded = expandedId === item.id;
            const statusColor = getStatusColor(item.status);

            return (
              <div
                key={item.id}
                onClick={(e) => isEditing ? openEditModal(item, e) : setExpandedId(isExpanded ? null : item.id)}
                className={`relative bg-[#162624]/90 backdrop-blur-md border rounded-2xl overflow-hidden transition-all duration-500 ease-out shadow-lg 
                    ${isExpanded ? 'h-auto border-primary/30' : 'h-36 border-white/5'} 
                    ${isEditing ? 'cursor-pointer hover:border-primary/50' : ''}`}
              >
                {/* Silk Texture Overlay */}
                <div className="absolute inset-0 opacity-[0.05] pointer-events-none" style={{ backgroundImage: 'radial-gradient(circle at center, white 1px, transparent 1px)', backgroundSize: '20px 20px' }}></div>

                <div className="relative z-10 p-4 h-full flex flex-col justify-between">

                  {/* Card Header Row */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-4">
                      {/* Jade Icon */}
                      <div className={`relative w-12 h-12 rounded-full flex items-center justify-center border-2 border-white/10 ${getStatusBg(item.status)}`}>
                        <div className={`absolute inset-0 rounded-full animate-pulse ${item.status === 'ACTIVE' || item.status === 'ALERT' ? 'bg-ochre/20' : 'bg-[#45b7aa]/20'}`}></div>
                        <span className={`material-symbols-outlined ${statusColor} text-2xl relative z-10`}>{item.icon}</span>
                      </div>

                      <div className="flex flex-col gap-1">
                        <h3 className="text-white text-lg font-bold font-serif tracking-wide flex items-center gap-2">
                          {item.title}
                          {isEditing && <span className="material-symbols-outlined text-xs text-slate-500">edit</span>}
                        </h3>
                        <span className={`text-[10px] font-bold uppercase tracking-wider ${statusColor} border border-current px-2 py-0.5 rounded-md inline-block self-start text-center min-w-[3rem]`}>
                          {getStatusLabel(item.status)}
                        </span>
                      </div>
                    </div>

                    {/* Top Value or Delete Button */}
                    {isEditing ? (
                      <button
                        onClick={(e) => handleDeleteClick(item.id, e)}
                        className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 flex items-center justify-center hover:bg-red-500 hover:text-white transition-all shadow-lg active:scale-95 z-20"
                      >
                        <span className="material-symbols-outlined text-xl">delete</span>
                      </button>
                    ) : (
                      !isExpanded && item.value && (
                        <div className="text-right mt-1">
                          <span className="text-white font-display font-bold text-xl">{item.value}</span>
                          {/* <span className="text-slate-400 text-xs ml-1">{item.unit}</span> */}
                        </div>
                      )
                    )}
                    {!isEditing && (
                      <span className={`material-symbols-outlined text-white/20 transition-transform duration-300 mt-2 ${isExpanded ? 'rotate-180' : ''}`}>expand_more</span>
                    )}
                  </div>

                  {/* Collapsed View Content */}
                  {!isExpanded && (
                    <>
                      {/* Middle Text Area */}
                      <div className="flex-1 flex flex-col justify-end relative z-10 pl-1 mt-2">
                        <div className="h-px w-8 bg-white/10 mb-3"></div>
                        <p className="text-[12px] text-slate-400 font-serif leading-relaxed opacity-90 line-clamp-1">
                          {item.dictum}
                        </p>
                      </div>

                      {/* Bottom Trend Line (Background) */}
                      <div className="absolute bottom-0 left-0 right-0 h-14 pointer-events-none opacity-40 z-0">
                        {renderTrendPath(item.trend, statusColor)}
                      </div>
                    </>
                  )}

                  {/* Expanded Content (Only visible when NOT editing) */}
                  {isExpanded && !isEditing && (
                    <div className="mt-4 pt-4 border-t border-white/5 animate-fade-in">
                      <div className="flex justify-between items-end mb-4">
                        <div>
                          <p className="text-slate-400 text-xs font-serif mb-1">当前监测值</p>
                          <div className="flex items-baseline gap-1">
                            <span className="text-white font-display font-bold text-3xl">{item.value || '--'}</span>
                            <span className="text-slate-400 text-sm">{item.unit}</span>
                          </div>
                        </div>
                        {/* Trend Visualization for Expanded */}
                        <div className="w-32 h-16 opacity-80">
                          {renderTrendPath(item.trend, statusColor)}
                        </div>
                      </div>

                      <div className="bg-black/20 rounded-lg p-3 border border-white/5">
                        <p className="text-slate-300 text-sm font-serif leading-relaxed text-justify">
                          {item.attribution}
                        </p>
                      </div>

                      <p className="text-[10px] text-slate-500 font-serif mt-3 text-center opacity-60">
                        — 豆包大模型 · 第一性原理推演 —
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Edit/Add Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#131b1d] border border-white/10 w-full max-w-sm rounded-2xl p-6 shadow-2xl relative">
            <h3 className="text-white font-serif text-xl font-bold mb-6 text-center tracking-wider">
              {editingItem.id ? '编辑档案' : '新增档案'}
            </h3>

            <div className="space-y-4">
              {/* Type Selection */}
              <div className="flex p-1 bg-black/30 rounded-lg">
                <button
                  onClick={() => setEditingItem({ ...editingItem, type: 'CHRONIC' })}
                  className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${editingItem.type === 'CHRONIC' ? 'bg-[#45b7aa] text-[#080c0d]' : 'text-slate-500'}`}
                >
                  慢性病
                </button>
                <button
                  onClick={() => setEditingItem({ ...editingItem, type: 'ALLERGY' })}
                  className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${editingItem.type === 'ALLERGY' ? 'bg-ochre text-[#080c0d]' : 'text-slate-500'}`}
                >
                  过敏/禁忌
                </button>
              </div>

              {/* Name Input */}
              <div>
                <label className="text-xs text-slate-400 mb-1 block">病史名称</label>
                <input
                  type="text"
                  value={editingItem.title || ''}
                  onChange={(e) => setEditingItem({ ...editingItem, title: e.target.value })}
                  placeholder="如：痛风、糖尿病..."
                  className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none text-sm"
                />
              </div>

              {/* Status Selection */}
              <div>
                <label className="text-xs text-slate-400 mb-1 block">当前状态</label>
                <select
                  value={editingItem.status}
                  onChange={(e) => setEditingItem({ ...editingItem, status: e.target.value as ConditionStatus })}
                  className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none text-sm appearance-none"
                >
                  <option value="ACTIVE">活跃 (需要关注)</option>
                  <option value="MONITORING">监测中 (日常控制)</option>
                  <option value="STABLE">平稳 (控制良好)</option>
                  <option value="ALERT">过敏 (绝对禁忌)</option>
                </select>
              </div>

              {/* Values - Show only for Chronic */}
              {editingItem.type === 'CHRONIC' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">数值 (选填)</label>
                    <input
                      type="text"
                      value={editingItem.value || ''}
                      onChange={(e) => setEditingItem({ ...editingItem, value: e.target.value })}
                      placeholder="420"
                      className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none text-sm font-display"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-1 block">单位 (选填)</label>
                    <input
                      type="text"
                      value={editingItem.unit || ''}
                      onChange={(e) => setEditingItem({ ...editingItem, unit: e.target.value })}
                      placeholder="μmol/L"
                      className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none text-sm"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={() => setShowModal(false)}
                className="flex-1 py-3 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                className="flex-1 py-3 rounded-xl bg-primary/20 border border-primary/20 text-primary font-bold text-sm hover:bg-primary/30 transition-colors shadow-[0_0_15px_rgba(17,196,212,0.2)]"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteId && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-[#131b1d] border border-white/10 w-full max-w-xs rounded-2xl p-6 shadow-2xl relative">
            <h3 className="text-white font-serif text-lg font-bold mb-2 text-center">确认删除</h3>
            <p className="text-slate-400 text-sm text-center mb-6">删除后，该病史的历史追踪数据将一并归档，无法直接恢复。</p>

            <div className="flex gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="flex-1 py-2.5 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors"
              >
                取消
              </button>
              <button
                onClick={confirmDelete}
                className="flex-1 py-2.5 rounded-xl bg-red-500/20 border border-red-500/20 text-red-400 font-bold text-sm hover:bg-red-500/30 transition-colors shadow-[0_0_15px_rgba(248,113,113,0.2)]"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MedicalArchivesView;