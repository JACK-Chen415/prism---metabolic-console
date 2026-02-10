import React, { useState } from 'react';
import { View } from '../../types';
import { AuthAPI, TokenManager } from '../../services/api';

interface RegisterViewProps {
    onViewChange: (view: View) => void;
    onRegisterSuccess?: (user: unknown) => void;
}

interface RegisterResponse {
    user: {
        id: number;
        phone: string;
        nickname: string;
    };
    tokens: {
        access_token: string;
        refresh_token: string;
    };
}

const RegisterView: React.FC<RegisterViewProps> = ({ onViewChange, onRegisterSuccess }) => {
    const [phone, setPhone] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [agreed, setAgreed] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const [showPassword, setShowPassword] = useState(false);
    const [shakeTerm, setShakeTerm] = useState(false);

    // Error Modal State
    const [errorMsg, setErrorMsg] = useState('');
    const [showError, setShowError] = useState(false);

    // Validation States
    const isPhoneValid = phone.length === 11;
    const isPasswordLengthValid = password.length >= 6 && password.length <= 20;
    const isPasswordMatch = password === confirmPassword && password !== '';
    const isFormValid = isPhoneValid && isPasswordLengthValid && isPasswordMatch && agreed;

    const handleRegister = async () => {
        if (!agreed) {
            setShakeTerm(true);
            setTimeout(() => setShakeTerm(false), 500);
            return;
        }

        if (!isFormValid) {
            if (!isPhoneValid) {
                setErrorMsg('请输入正确的11位手机号');
            } else if (!isPasswordLengthValid) {
                setErrorMsg('密码长度需要6-20位');
            } else if (!isPasswordMatch) {
                setErrorMsg('两次输入的密码不一致');
            }
            setShowError(true);
            return;
        }

        // 调用真实API注册
        setIsLoading(true);
        try {
            const response = await AuthAPI.register(phone, password) as RegisterResponse;

            // 保存 Token
            TokenManager.setTokens(
                response.tokens.access_token,
                response.tokens.refresh_token
            );

            // 通知父组件注册成功（handleAuthSuccess 内部会跳转到首页）
            if (onRegisterSuccess) {
                onRegisterSuccess(response.user);
            } else {
                // fallback: 如无回调则直接跳转
                onViewChange(View.HOME);
            }
        } catch (error) {
            setErrorMsg(error instanceof Error ? error.message : '注册失败，请重试');
            setShowError(true);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col w-full min-h-[100dvh] bg-[#080c0d] relative animate-fade-in">
            <style>{`
        /* Hide native password reveal button in Edge/IE */
        input::-ms-reveal,
        input::-ms-clear {
            display: none;
        }
        /* Hide spin buttons for number inputs (verification code) */
        input[type=number]::-webkit-inner-spin-button, 
        input[type=number]::-webkit-outer-spin-button { 
            -webkit-appearance: none; 
            margin: 0; 
        }
        input[type=number] {
            -moz-appearance: textfield;
        }
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            20% { transform: translateX(-4px); }
            40% { transform: translateX(4px); }
            60% { transform: translateX(-4px); }
            80% { transform: translateX(4px); }
        }
      `}</style>

            {/* 1. Header */}
            <div className="pt-12 px-6 pb-4 flex items-start gap-4 shrink-0">
                <button
                    onClick={() => onViewChange(View.LOGIN)}
                    className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors -ml-3 mt-1"
                >
                    <span className="material-symbols-outlined text-white">arrow_back</span>
                </button>
                <div className="flex flex-col">
                    <h1 className="text-white text-2xl font-serif font-bold tracking-wide">创建账号</h1>
                    <p className="text-slate-400 text-xs font-serif mt-1 tracking-wide">开启您的代谢管理之旅</p>
                </div>
            </div>

            {/* 2. Form Area - Vertically Centered */}
            <div className="flex-1 px-8 flex flex-col justify-center pb-8">

                {/* Error Popup Modal */}
                {showError && (
                    <div className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/60 backdrop-blur-sm animate-fade-in">
                        <div className="bg-[#131b1d] border border-white/10 rounded-2xl p-6 shadow-2xl w-full max-w-xs flex flex-col items-center">
                            <div className="w-12 h-12 rounded-full bg-ochre/10 flex items-center justify-center mb-4 text-ochre border border-ochre/20">
                                <span className="material-symbols-outlined text-2xl">error</span>
                            </div>
                            <h3 className="text-white font-serif font-bold text-lg mb-2 tracking-wide">提示</h3>
                            <p className="text-slate-400 text-sm font-serif text-center mb-6 tracking-wide leading-relaxed">
                                {errorMsg}
                            </p>
                            <button
                                onClick={() => setShowError(false)}
                                className="w-full py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold font-serif tracking-wide transition-colors"
                            >
                                我知道了
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 1: Phone */}
                <div className="mb-10">
                    <h3 className="text-white/40 text-[10px] font-serif font-bold uppercase tracking-widest mb-5">手机号</h3>
                    <div className="space-y-6">
                        {/* Phone */}
                        <div className="relative group">
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                                <span className="material-symbols-outlined text-xl">smartphone</span>
                            </div>
                            <input
                                type="tel"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 11))}
                                placeholder="请输入11位手机号"
                                maxLength={11}
                                className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-4 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                            />
                        </div>
                    </div>
                </div>

                {/* Step 2: Security */}
                <div className="mb-8">
                    <h3 className="text-white/40 text-[10px] font-serif font-bold uppercase tracking-widest mb-5">密码设置</h3>
                    <div className="space-y-6">
                        {/* Password */}
                        <div className="relative group">
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                                <span className="material-symbols-outlined text-xl">lock</span>
                            </div>
                            <input
                                type={showPassword ? "text" : "password"}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="设置 6-20 位密码"
                                className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-10 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                            />
                            <button
                                onClick={() => setShowPassword(!showPassword)}
                                className="absolute right-0 top-3 text-slate-500 hover:text-white transition-colors"
                                tabIndex={-1} // Prevent tabbing to this if we want specific flow, but generally optional
                            >
                                <span className="material-symbols-outlined text-lg">{showPassword ? 'visibility_off' : 'visibility'}</span>
                            </button>
                        </div>

                        {/* Confirm Password with Real-time Validation */}
                        <div className="relative group">
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                                <span className="material-symbols-outlined text-xl">lock_reset</span>
                            </div>

                            {/* Border Color Logic based on Validation */}
                            <input
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                placeholder="再次输入密码"
                                className={`w-full bg-[#162624]/60 border-b text-white pl-8 pr-10 py-3 outline-none transition-all placeholder-slate-600 font-serif tracking-wide
                            ${!confirmPassword
                                        ? 'border-white/10 focus:border-[#45b7aa]'
                                        : isPasswordMatch
                                            ? 'border-[#45b7aa]'
                                            : 'border-ochre'
                                    }
                        `}
                            />

                            {/* Status Icon */}
                            {confirmPassword && (
                                <div className="absolute right-0 top-3 pointer-events-none animate-fade-in">
                                    <span className={`material-symbols-outlined text-lg ${isPasswordMatch ? 'text-[#45b7aa]' : 'text-ochre'}`}>
                                        {isPasswordMatch ? 'check_circle' : 'cancel'}
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* CTA Button */}
                <button
                    onClick={handleRegister}
                    disabled={!isFormValid || isLoading}
                    className={`w-full mt-6 h-12 rounded-xl font-serif font-bold tracking-wide transition-all relative overflow-hidden flex items-center justify-center gap-2
                ${isFormValid && !isLoading
                            ? 'bg-[#45b7aa] text-white shadow-[0_0_20px_rgba(69,183,170,0.3)] hover:shadow-[0_0_30px_rgba(69,183,170,0.5)] active:scale-[0.98]'
                            : 'bg-white/10 text-white/30 cursor-not-allowed'
                        }
            `}
                >
                    {isLoading ? (
                        <span className="flex items-center gap-2">
                            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                            注册中...
                        </span>
                    ) : (
                        <>
                            完成注册
                            {isFormValid && <span className="material-symbols-outlined text-sm">arrow_forward</span>}
                        </>
                    )}
                </button>

            </div>

            {/* 3. Footer: Agreement - Fixed bottom */}
            <div className="px-8 pb-10 flex justify-center shrink-0">
                <div
                    className={`flex items-start gap-2 cursor-pointer transition-transform ${shakeTerm ? 'animate-[shake_0.5s_ease-in-out]' : ''}`}
                    onClick={() => setAgreed(!agreed)}
                >
                    <div className={`mt-0.5 w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${agreed ? 'bg-[#45b7aa] border-[#45b7aa]' : 'border-slate-500 hover:border-white'}`}>
                        {agreed && <span className="material-symbols-outlined text-[10px] text-[#080c0d] font-bold">check</span>}
                    </div>
                    <p className={`text-[10px] leading-tight font-serif tracking-wide ${shakeTerm ? 'text-ochre' : 'text-slate-500'}`}>
                        我已阅读并同意 <span className="text-[#45b7aa] hover:underline">《用户协议》</span> 与 <span className="text-[#45b7aa] hover:underline">《隐私政策》</span>
                    </p>
                </div>
            </div>
        </div>
    );
};

export default RegisterView;