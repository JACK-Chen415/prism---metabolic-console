import React, { useState, useEffect } from 'react';
import { View } from '../../types';
import { AuthAPI, TokenManager } from '../../services/api';

interface LoginViewProps {
    onViewChange: (view: View) => void;
    onSkipLogin?: () => void;
    onLoginSuccess?: (user: unknown) => void;
}

interface LoginResponse {
    user: {
        id: number;
        phone: string;
        nickname: string;
        gender?: string;
        age?: number;
        height?: number;
        weight?: number;
    };
    tokens: {
        access_token: string;
        refresh_token: string;
    };
}

const LoginView: React.FC<LoginViewProps> = ({ onViewChange, onSkipLogin, onLoginSuccess }) => {
    const [loginMethod, setLoginMethod] = useState<'CODE' | 'PASSWORD'>('PASSWORD'); // 默认密码登录
    const [phone, setPhone] = useState('');
    const [code, setCode] = useState('');
    const [password, setPassword] = useState('');
    const [countdown, setCountdown] = useState(0);
    const [isLoading, setIsLoading] = useState(false);

    // Error Modal State
    const [errorMsg, setErrorMsg] = useState('');
    const [showError, setShowError] = useState(false);

    // Countdown timer logic
    useEffect(() => {
        if (countdown > 0) {
            const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
            return () => clearTimeout(timer);
        }
    }, [countdown]);

    const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        // Only allow numeric input, max 11 digits
        const value = e.target.value.replace(/\D/g, '').slice(0, 11);
        setPhone(value);
    };

    const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        // Only allow numeric input, max 6 digits
        const value = e.target.value.replace(/\D/g, '').slice(0, 6);
        setCode(value);
    };

    const handleGetCode = () => {
        if (phone.length !== 11) {
            setErrorMsg('手机号输入错误');
            setShowError(true);
            return;
        }
        if (countdown > 0) return;
        setCountdown(60);
    };

    const handleLogin = async () => {
        // Validation Logic on Click
        if (phone.length !== 11) {
            setErrorMsg('请输入正确的11位手机号');
            setShowError(true);
            return;
        }

        if (loginMethod === 'CODE') {
            if (code.length !== 6) {
                setErrorMsg('验证码输入错误');
                setShowError(true);
                return;
            }
            // 验证码登录暂不支持
            setErrorMsg('验证码登录功能暂未开放，请使用密码登录');
            setShowError(true);
            return;
        } else {
            if (!password || password.length < 6) {
                setErrorMsg('请输入至少6位密码');
                setShowError(true);
                return;
            }
        }

        // 调用真实API登录
        setIsLoading(true);
        try {
            const response = await AuthAPI.login(phone, password) as LoginResponse;

            // 保存 Token
            TokenManager.setTokens(
                response.tokens.access_token,
                response.tokens.refresh_token
            );

            // 通知父组件登录成功（handleAuthSuccess 内部会跳转到首页）
            if (onLoginSuccess) {
                onLoginSuccess(response.user);
            } else {
                // fallback: 如无回调则直接跳转
                onViewChange(View.HOME);
            }
        } catch (error) {
            setErrorMsg(error instanceof Error ? error.message : '登录失败，请重试');
            setShowError(true);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col w-full h-[100dvh] bg-[#080c0d] relative animate-fade-in overflow-hidden">
            <style>{`
        /* Hide native password reveal button in Edge/IE */
        input::-ms-reveal,
        input::-ms-clear {
            display: none;
        }
      `}</style>

            {/* Error Popup Modal */}
            {showError && (
                <div className="absolute inset-0 z-50 flex items-center justify-center p-8 bg-black/60 backdrop-blur-sm animate-fade-in">
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

            {/* Skip Button */}
            {onSkipLogin && (
                <button
                    onClick={onSkipLogin}
                    className="absolute top-6 right-6 z-20 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-slate-400 hover:text-white hover:bg-white/10 transition-colors backdrop-blur-sm flex items-center gap-1 font-serif"
                >
                    跳过
                    <span className="material-symbols-outlined text-[10px]">arrow_forward_ios</span>
                </button>
            )}

            {/* 1. Header: Brand - More Compact */}
            <div className="pt-12 pb-6 w-full flex flex-col items-center justify-center relative shrink-0">
                {/* Glow Background */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 bg-[#45b7aa]/10 rounded-full blur-[60px]"></div>

                {/* Logo */}
                <div className="relative mb-4">
                    <svg className="w-14 h-14 drop-shadow-[0_0_20px_rgba(17,196,212,0.4)] animate-pulse" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" style={{ animationDuration: '4s' }}>
                        <defs>
                            <linearGradient gradientUnits="userSpaceOnUse" id="prism_login_1" x1="12" x2="2" y1="2" y2="19">
                                <stop stopColor="#11c4d4" stopOpacity="0.9"></stop>
                                <stop offset="1" stopColor="#11c4d4" stopOpacity="0.1"></stop>
                            </linearGradient>
                            <linearGradient gradientUnits="userSpaceOnUse" id="prism_login_2" x1="12" x2="22" y1="2" y2="19">
                                <stop stopColor="#7aa0a0" stopOpacity="0.9"></stop>
                                <stop offset="1" stopColor="#7aa0a0" stopOpacity="0.1"></stop>
                            </linearGradient>
                        </defs>
                        <path d="M12 2L2 19L12 14L12 2Z" fill="url(#prism_login_1)"></path>
                        <path d="M12 2L22 19L12 14L12 2Z" fill="url(#prism_login_2)"></path>
                        <path d="M2 19L12 14L22 19" fill="rgba(8,12,13,0.5)"></path>
                    </svg>
                </div>

                <h1 className="text-white text-3xl font-serif tracking-widest mb-1 font-light">食鉴</h1>
                <p className="text-white/50 text-[10px] font-serif tracking-[0.4em] font-medium uppercase">PRISM</p>
            </div>

            {/* 2. Core Form - Flexibly centered */}
            <div className="flex-1 px-8 flex flex-col justify-center min-h-0">
                {/* Tabs */}
                <div className="flex gap-8 mb-8 justify-center shrink-0">
                    <button
                        onClick={() => setLoginMethod('CODE')}
                        className={`pb-2 text-sm font-serif font-medium transition-all relative ${loginMethod === 'CODE' ? 'text-[#45b7aa] font-bold' : 'text-slate-500'}`}
                    >
                        验证码登录
                        {loginMethod === 'CODE' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#45b7aa] rounded-full"></div>}
                    </button>
                    <button
                        onClick={() => setLoginMethod('PASSWORD')}
                        className={`pb-2 text-sm font-serif font-medium transition-all relative ${loginMethod === 'PASSWORD' ? 'text-[#45b7aa] font-bold' : 'text-slate-500'}`}
                    >
                        密码登录
                        {loginMethod === 'PASSWORD' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#45b7aa] rounded-full"></div>}
                    </button>
                </div>

                {/* Inputs */}
                <div className="space-y-6 shrink-0">
                    {/* Phone Input */}
                    <div className="relative group">
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                            <span className="material-symbols-outlined text-xl">smartphone</span>
                        </div>
                        <input
                            type="tel"
                            value={phone}
                            onChange={handlePhoneChange}
                            placeholder="请输入手机号"
                            maxLength={11}
                            className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-4 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide text-sm"
                        />
                    </div>

                    {loginMethod === 'CODE' ? (
                        // Code Input
                        <div className="relative group">
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                                <span className="material-symbols-outlined text-xl">shield</span>
                            </div>
                            <input
                                type="tel"
                                value={code}
                                onChange={handleCodeChange}
                                placeholder="请输入验证码"
                                maxLength={6}
                                className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-24 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide text-sm"
                            />
                            <button
                                onClick={handleGetCode}
                                className={`absolute right-0 top-1/2 -translate-y-1/2 text-xs font-serif font-bold px-3 py-1.5 rounded-md transition-colors ${countdown > 0 ? 'text-slate-500 cursor-not-allowed' : 'text-ochre hover:bg-ochre/10'}`}
                            >
                                {countdown > 0 ? `${countdown}s` : '获取验证码'}
                            </button>
                        </div>
                    ) : (
                        // Password Input
                        <div className="relative group">
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                                <span className="material-symbols-outlined text-xl">lock</span>
                            </div>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="请输入密码"
                                className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-4 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide text-sm"
                            />
                        </div>
                    )}
                </div>

                {/* CTA Button */}
                <button
                    onClick={handleLogin}
                    disabled={isLoading}
                    className={`w-full mt-10 h-12 rounded-xl font-serif font-bold tracking-wide shadow-lg transition-all relative overflow-hidden group shrink-0 flex items-center justify-center ${isLoading ? 'bg-[#45b7aa]/50 cursor-not-allowed' : 'bg-[#45b7aa] active:scale-[0.98] hover:shadow-[0_0_30px_rgba(69,183,170,0.5)]'} text-white shadow-[0_0_20px_rgba(69,183,170,0.3)]`}
                >
                    <div className="absolute inset-0 bg-gradient-to-tr from-white/20 to-transparent opacity-0 transition-opacity group-hover:opacity-100"></div>
                    {isLoading ? (
                        <span className="flex items-center gap-2">
                            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                            登录中...
                        </span>
                    ) : '登录'}
                </button>

                {/* Aux Links */}
                <div className="flex justify-between mt-6 px-1 shrink-0">
                    <button
                        onClick={() => onViewChange(View.FORGOT_PASSWORD)}
                        className="text-xs text-slate-500 hover:text-white transition-colors font-serif font-medium tracking-wide"
                    >
                        忘记密码
                    </button>
                    <button
                        onClick={() => onViewChange(View.REGISTER)}
                        className="text-xs text-[#45b7aa] font-bold hover:text-[#45b7aa]/80 transition-colors flex items-center gap-0.5 font-serif tracking-wide"
                    >
                        注册新账号
                        <span className="material-symbols-outlined text-[10px]">arrow_forward</span>
                    </button>
                </div>
            </div>

            {/* Spacer to keep layout balanced without footer */}
            <div className="h-8 shrink-0"></div>
        </div>
    );
};

export default LoginView;