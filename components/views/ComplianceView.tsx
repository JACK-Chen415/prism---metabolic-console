import React from 'react';
import { ComplianceDocument, ComplianceDocumentKey } from '../../types';
import { COMPLIANCE_MEDICAL_DISCLAIMER } from '../../constants/compliance';

export { COMPLIANCE_MEDICAL_DISCLAIMER };

export const COMPLIANCE_DOCUMENT_ORDER: ComplianceDocumentKey[] = [
    'terms',
    'privacy',
    'ai_use',
    'health_disclaimer',
    'data_rights',
];

export const COMPLIANCE_DOCUMENTS: Record<ComplianceDocumentKey, ComplianceDocument> = {
    terms: {
        key: 'terms',
        title: '用户协议',
        shortTitle: '协议',
        subtitle: '使用 Prism 前，请理解服务边界、账号责任和内容限制。',
        sections: [
            {
                heading: '服务定位',
                body: 'Prism Metabolic Console 帮助你记录餐食、查看营养估算、整理健康档案并获得代谢管理提醒。所有结果仅用于个人健康管理参考，不提供医疗诊断，也不构成治疗建议、处方或医生意见。',
            },
            {
                heading: '账号与资料',
                bullets: [
                    '你需要保证手机号、身体参数、慢病/过敏、饮食记录等信息尽量真实、准确、及时更新。',
                    '若资料不完整或输入有误，热量、钠、嘌呤、过敏风险和 AI 提示可能不准确。',
                    '请妥善保管账号和设备，不要让他人使用你的账号记录敏感健康信息。',
                ],
            },
            {
                heading: '合理使用',
                bullets: [
                    '不得上传违法、侵权、欺诈、恶意代码或与健康管理无关的内容。',
                    '不得将 Prism 输出作为诊断、治疗、开药、停药或急救依据。',
                    '如出现胸痛、呼吸困难、严重过敏、低血糖等紧急情况，请立即联系急救或线下医疗机构。',
                ],
            },
            {
                heading: '服务变更',
                body: 'Prism 可能根据安全、合规、模型能力或产品策略调整功能。涉及用户权利或重要限制的内容，会尽量在产品内提供清晰入口。',
            },
        ],
    },
    privacy: {
        key: 'privacy',
        title: '隐私政策',
        shortTitle: '隐私',
        subtitle: '说明 Prism 如何处理账号、饮食、健康档案和 AI 交互数据。',
        sections: [
            {
                heading: '我们可能处理的数据',
                bullets: [
                    '账号信息：手机号、登录状态、昵称、头像等。',
                    '健康与身体资料：年龄、性别、身高、体重、慢病标签、过敏信息、每日目标等。',
                    '饮食与交互数据：餐食记录、图片识别结果、文字/语音转写内容、AI 对话、系统提醒和本地离线缓存。',
                    '技术信息：请求时间、同步状态、错误信息和必要的安全日志。',
                ],
            },
            {
                heading: '使用目的',
                bullets: [
                    '提供登录、记录、同步、导出、删除、消息提醒和偏好设置等基础功能。',
                    '用于营养估算、风险提示、AI 辅助解释和产品安全改进。',
                    '在你使用图片、文字或 AI 功能时，必要数据可能被发送到后端或模型服务进行处理。',
                ],
            },
            {
                heading: '存储与安全',
                body: 'Prism 会通过访问令牌、用户隔离、本地缓存清理等方式降低数据泄露风险。但任何联网服务都无法保证绝对安全，请避免上传不必要的身份证件、完整病历或高度敏感资料。',
            },
            {
                heading: '你的选择',
                bullets: [
                    '你可以在设置中导出个人数据、提交数据删除请求或发起账户注销请求。',
                    '你可以更新身体参数、慢病/过敏资料，也可以退出登录以清理本地敏感缓存。',
                    '数据删除或账户注销可能因法律、安全、纠纷处理或备份周期保留必要记录。',
                ],
            },
        ],
    },
    ai_use: {
        key: 'ai_use',
        title: 'AI 使用说明',
        shortTitle: 'AI',
        subtitle: '解释 AI 分析、图片识别和健康提示的能力边界。',
        sections: [
            {
                heading: 'AI 输出的性质',
                body: 'AI 会基于你输入的餐食、图片、健康档案和系统规则生成解释或建议。AI 可能遗漏、误判、过度概括或受到输入质量影响，不能替代医生、营养师或药师。',
            },
            {
                heading: '营养估算限制',
                bullets: [
                    '热量、钠、嘌呤、蛋白质等数值是估算值，可能与真实烹饪、品牌、分量和调味方式存在差异。',
                    '图片识别可能无法准确区分食材、调料、烹饪油量或隐藏配料。',
                    'AI 对慢病、过敏或药物相互作用的提示仅是风险提醒，不是诊断或治疗方案。',
                ],
            },
            {
                heading: '使用建议',
                bullets: [
                    '用于日常记录、复盘趋势和准备与医生/营养师沟通的问题清单。',
                    '涉及疾病诊断、治疗、用药、停药、手术、急救或孕产等情形，请直接咨询医疗专业人员。',
                    '发现 AI 输出明显不合理时，请以产品内可编辑记录、线下检测结果和医生意见为准。',
                ],
            },
        ],
    },
    health_disclaimer: {
        key: 'health_disclaimer',
        title: '健康免责声明',
        shortTitle: '免责声明',
        subtitle: '明确 Prism 的健康管理边界和高风险场景处理方式。',
        sections: [
            {
                heading: '非医疗服务',
                body: COMPLIANCE_MEDICAL_DISCLAIMER,
            },
            {
                heading: '高风险情况',
                bullets: [
                    '急性疼痛、严重过敏、昏厥、持续呕吐、呼吸困难、疑似中毒等情况请立即就医。',
                    '糖尿病、痛风、肾病、心血管疾病、妊娠、儿童或老年人等特殊人群，应在医生或营养师指导下使用饮食建议。',
                    '任何检测指标异常、药物调整、治疗方案选择，都不应仅依据 Prism 的估算或 AI 回复。',
                ],
            },
            {
                heading: '个人责任',
                body: '你理解并同意，Prism 提供的信息仅为辅助记录和一般性健康教育。你应结合自身情况、线下检测、医生建议和当地法律法规独立判断。',
            },
        ],
    },
    data_rights: {
        key: 'data_rights',
        title: '数据导出与删除说明',
        shortTitle: '数据权利',
        subtitle: '说明如何导出数据、删除数据和注销账户。',
        sections: [
            {
                heading: '导出数据',
                bullets: [
                    '你可以在设置中导出账号资料、饮食记录、健康档案、消息和 AI 洞察等数据。',
                    '导出文件仅用于个人留存、迁移或与专业人士沟通，不是医疗诊断、治疗或病历文件。',
                    '若部分后端接口暂不可用，导出文件会保留相应错误信息，避免静默遗漏。',
                ],
            },
            {
                heading: '删除数据',
                bullets: [
                    '删除数据入口用于提交删除账号相关饮食记录、健康档案、AI 对话和本地缓存的请求。',
                    '本地缓存可立即清理；云端删除需后端受理并可能受备份、安全审计、法定义务或争议处理限制。',
                    '删除后，Prism 的历史趋势、提醒和 AI 上下文可能无法恢复。',
                ],
            },
            {
                heading: '注销账户',
                bullets: [
                    '注销账户会发起更高风险的账号关闭流程，完成后你将无法继续使用原账号登录。',
                    '建议先导出个人数据，再提交注销请求。',
                    '注销不代表 Prism 曾提供医疗诊断或治疗，也不替代线下医疗记录保存。',
                ],
            },
        ],
    },
};

interface ComplianceViewProps {
    activeDocument: ComplianceDocumentKey;
    onDocumentChange?: (documentKey: ComplianceDocumentKey) => void;
    onClose: () => void;
}

const ComplianceView: React.FC<ComplianceViewProps> = ({
    activeDocument,
    onDocumentChange,
    onClose,
}) => {
    const document = COMPLIANCE_DOCUMENTS[activeDocument];

    return (
        <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm animate-fade-in sm:items-center sm:p-4">
            <button
                type="button"
                aria-label="关闭合规说明"
                className="absolute inset-0 h-full w-full"
                onClick={onClose}
            />
            <section
                role="dialog"
                aria-modal="true"
                aria-labelledby="compliance-title"
                className="relative flex h-[92dvh] w-full max-w-md flex-col overflow-hidden rounded-t-3xl border border-white/10 bg-[#0d1517] shadow-2xl shadow-black/50 sm:h-[86dvh] sm:rounded-3xl"
            >
                <div className="absolute inset-0 pointer-events-none bg-[url('/images/bg-texture.png')] bg-cover opacity-10 mix-blend-soft-light" />

                <header className="relative shrink-0 border-b border-white/5 px-4 pb-3 pt-4">
                    <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                            <p className="text-[10px] font-display tracking-[0.22em] text-primary/60">
                                COMPLIANCE
                            </p>
                            <h2 id="compliance-title" className="mt-1 text-xl font-bold text-white font-serif tracking-wide">
                                {document.title}
                            </h2>
                            <p className="mt-1 text-xs leading-5 text-slate-400 font-serif tracking-wide">
                                {document.subtitle}
                            </p>
                        </div>
                        <button
                            type="button"
                            aria-label="关闭"
                            onClick={onClose}
                            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white/50 transition-colors hover:bg-white/10 hover:text-white"
                        >
                            <span className="material-symbols-outlined text-xl">close</span>
                        </button>
                    </div>
                </header>

                <nav className="relative shrink-0 overflow-x-auto border-b border-white/5 px-4 py-3 no-scrollbar" aria-label="合规文档">
                    <div className="flex min-w-max gap-2">
                        {COMPLIANCE_DOCUMENT_ORDER.map((key) => {
                            const item = COMPLIANCE_DOCUMENTS[key];
                            const isActive = key === activeDocument;
                            return (
                                <button
                                    key={key}
                                    type="button"
                                    onClick={() => onDocumentChange?.(key)}
                                    className={`h-9 rounded-full border px-3 text-xs font-bold font-serif tracking-wide transition-colors ${
                                        isActive
                                            ? 'border-primary/40 bg-primary/15 text-primary'
                                            : 'border-white/10 bg-white/[0.03] text-white/50 hover:bg-white/[0.07] hover:text-white/80'
                                    }`}
                                >
                                    {item.shortTitle}
                                </button>
                            );
                        })}
                    </div>
                </nav>

                <div className="relative flex-1 overflow-y-auto px-5 pb-8 pt-4">
                    <div className="mb-4 rounded-xl border border-ochre/20 bg-ochre/10 p-3">
                        <div className="flex gap-2">
                            <span className="material-symbols-outlined text-base text-ochre">medical_information</span>
                            <p className="text-xs leading-5 text-ochre/90 font-serif tracking-wide">
                                {COMPLIANCE_MEDICAL_DISCLAIMER}
                            </p>
                        </div>
                    </div>

                    <div className="space-y-4">
                        {document.sections.map((section) => (
                            <article key={section.heading} className="rounded-xl border border-white/8 bg-white/[0.035] p-4">
                                <h3 className="text-sm font-bold text-white font-serif tracking-wide">
                                    {section.heading}
                                </h3>
                                {section.body && (
                                    <p className="mt-2 text-xs leading-6 text-slate-300 font-serif tracking-wide">
                                        {section.body}
                                    </p>
                                )}
                                {section.bullets && (
                                    <ul className="mt-2 space-y-2">
                                        {section.bullets.map((item) => (
                                            <li key={item} className="flex gap-2 text-xs leading-6 text-slate-300 font-serif tracking-wide">
                                                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
                                                <span>{item}</span>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </article>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
};

export default ComplianceView;
