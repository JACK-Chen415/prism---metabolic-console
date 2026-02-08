import React, { useState, useEffect } from 'react';
import { View } from '../../types';

interface ForgotPasswordViewProps {
  onViewChange: (view: View) => void;
}

const ForgotPasswordView: React.FC<ForgotPasswordViewProps> = ({ onViewChange }) => {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isSuccess, setIsSuccess] = useState(false);
  const [showError, setShowError] = useState(false);

  // Validation
  const isPhoneValid = phone.length >= 11;
  const passwordsMatch = password === confirmPassword && password.length > 0;
  
  // Simulated existing user check
  const isUserRegistered = true; // In real app, this would be an API call

  // Strength calculation: 0 (None), 1 (Weak), 2 (Medium), 3 (Strong)
  const getStrength = (pwd: string) => {
    if (!pwd) return 0;
    if (pwd.length < 8) return 1;
    if (pwd.length < 12 && /[A-Za-z]/.test(pwd) && /[0-9]/.test(pwd)) return 2;
    if (pwd.length >= 12 && /[A-Za-z]/.test(pwd) && /[0-9]/.test(pwd)) return 3;
    return 1;
  };
  const strength = getStrength(password);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const handleGetCode = () => {
    if (!isPhoneValid) return;
    
    // Simulate check
    if (!isUserRegistered) {
        setShowError(true);
        setTimeout(() => setShowError(false), 3000);
        return;
    }
    setCountdown(60);
  };

  const handleSubmit = () => {
     if (isPhoneValid && code.length >= 4 && passwordsMatch && strength > 0) {
        setIsSuccess(true);
        setTimeout(() => {
           onViewChange(View.HOME);
        }, 3000);
     }
  };

  if (isSuccess) {
      // Success Animation View: Prism Aggregation
      return (
          <div className="flex flex-col items-center justify-center w-full h-[100dvh] bg-[#080c0d] relative overflow-hidden animate-fade-in">
              {/* Prism Animation */}
              <div className="relative w-64 h-64 flex items-center justify-center">
                  <div className="absolute inset-0 bg-[#45b7aa]/20 blur-[60px] rounded-full animate-pulse"></div>
                  <svg className="w-32 h-32 drop-shadow-[0_0_30px_rgba(69,183,170,0.6)] animate-bounce" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M12 2L2 19L12 14L12 2Z" fill="#45b7aa" fillOpacity="0.9" className="animate-[pulse_1s_ease-in-out_infinite]"></path>
                      <path d="M12 2L22 19L12 14L12 2Z" fill="#7aa0a0" fillOpacity="0.9" className="animate-[pulse_1.5s_ease-in-out_infinite]"></path>
                  </svg>
              </div>
              <h2 className="text-[#45b7aa] text-xl font-serif font-bold tracking-widest mt-6 animate-[fade-in_1s_ease-out]">密钥已更新</h2>
          </div>
      );
  }

  return (
    <div className="flex flex-col w-full min-h-[100dvh] bg-[#080c0d] relative animate-fade-in overflow-hidden">
        <style>{`
        /* Hide native password reveal button */
        input::-ms-reveal, input::-ms-clear { display: none; }
        /* Hide number spin buttons */
        input[type=number]::-webkit-inner-spin-button, 
        input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
        input[type=number] { -moz-appearance: textfield; }
        `}</style>
        
        {/* Light Beam Effect */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[120%] h-[50vh] bg-gradient-to-b from-white/5 via-transparent to-transparent pointer-events-none blur-3xl z-0"></div>

        {/* Header */}
        <div className="pt-12 px-8 pb-8 flex flex-col gap-1 z-10 shrink-0">
            <button 
                onClick={() => onViewChange(View.LOGIN)} 
                className="w-10 h-10 -ml-3 mb-6 rounded-full flex items-center justify-center hover:bg-white/5 transition-colors group"
            >
                <span className="material-symbols-outlined text-white/80 group-hover:text-white">arrow_back</span>
            </button>
            <h1 className="text-white text-3xl font-serif font-bold tracking-wide">重置密码</h1>
            <p className="text-[#45b7aa] text-xs font-serif tracking-[0.1em] font-medium opacity-90">身份验证与安全校准</p>
        </div>

        {/* 3-Step Form */}
        <div className="px-8 flex flex-col gap-8 z-10 flex-1">
            
            {/* Step 1: Identity Index */}
            <div className="space-y-1">
                <div className="relative group">
                     <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                        <span className="material-symbols-outlined text-xl">smartphone</span>
                    </div>
                    <input 
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="请输入注册手机号"
                        className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-4 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                    />
                </div>
                {showError && (
                    <div className="text-[10px] text-ochre mt-1 flex items-center gap-1 animate-fade-in font-serif tracking-wide">
                        <span>该通讯ID未收录，请前往</span>
                        <button onClick={() => onViewChange(View.REGISTER)} className="underline font-bold">注册</button>
                    </div>
                )}
            </div>

            {/* Step 2: Token Verification */}
             <div className="relative group">
                <div className="absolute left-0 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-[#45b7aa] transition-colors">
                    <span className="material-symbols-outlined text-xl">mark_email_unread</span>
                </div>
                <input 
                    type="number"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="请输入验证码"
                    className="w-full bg-[#162624]/60 border-b border-white/10 text-white pl-8 pr-24 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                />
                <button 
                    onClick={handleGetCode}
                    disabled={countdown > 0 || !isPhoneValid}
                    className={`absolute right-0 top-1/2 -translate-y-1/2 text-xs font-bold transition-colors font-serif tracking-wide ${
                        countdown > 0 
                        ? 'text-ochre' 
                        : isPhoneValid ? 'text-[#45b7aa] hover:text-[#45b7aa]/80' : 'text-slate-600 cursor-not-allowed'
                    }`}
                >
                    {countdown > 0 ? `${countdown}s` : '获取验证码'}
                </button>
            </div>

            {/* Step 3: New Key Configuration */}
            <div className="space-y-6">
                 {/* New Password */}
                 <div className="relative group">
                    <label className="text-[10px] text-white/40 uppercase tracking-wider mb-1 block font-serif font-bold">设置新的密码</label>
                    <input 
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="设置新密码"
                        className="w-full bg-[#162624]/60 border-b border-white/10 text-white px-0 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                    />
                    {/* Energy Bar Strength Meter */}
                    <div className="flex gap-1.5 mt-2 h-1 w-full overflow-hidden">
                        <div 
                            className={`h-full rounded-full transition-all duration-500 ease-out ${
                                strength === 0 ? 'w-0' :
                                strength === 1 ? 'w-1/4 bg-ochre' :
                                strength === 2 ? 'w-1/2 bg-slate-400' :
                                'w-full bg-[#45b7aa] shadow-[0_0_8px_rgba(69,183,170,0.6)]'
                            }`}
                        ></div>
                    </div>
                    {password && (
                        <p className={`text-[10px] mt-1 transition-colors font-serif tracking-wide ${
                            strength === 1 ? 'text-ochre' : strength === 2 ? 'text-slate-400' : 'text-[#45b7aa]'
                        }`}>
                            {strength === 1 ? '弱 - 建议更长' : strength === 2 ? '中 - 尚可' : '强 - 安全'}
                        </p>
                    )}
                 </div>

                 {/* Confirm Password */}
                 <div className="relative group">
                     <input 
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="确认新密码"
                        className="w-full bg-[#162624]/60 border-b border-white/10 text-white px-0 py-3 outline-none focus:border-[#45b7aa] transition-colors placeholder-slate-600 font-serif tracking-wide"
                     />
                     {/* Green Lock Animation */}
                     <div className={`absolute right-0 top-3 transition-all duration-500 transform ${passwordsMatch ? 'opacity-100 scale-100' : 'opacity-0 scale-50'}`}>
                         <span className="material-symbols-outlined text-[#45b7aa] drop-shadow-[0_0_8px_rgba(69,183,170,0.4)]">lock</span>
                     </div>
                 </div>
            </div>
        </div>

        {/* Action - Floating at bottom */}
        <div className="px-8 pb-10 pt-4 z-20">
             <button 
                onClick={handleSubmit}
                disabled={!isPhoneValid || !code || !passwordsMatch || strength === 0}
                className={`w-full h-14 rounded-2xl font-serif font-bold tracking-widest text-sm transition-all duration-300 relative overflow-hidden backdrop-blur-md border border-white/5
                    ${(!isPhoneValid || !code || !passwordsMatch || strength === 0)
                        ? 'bg-white/5 text-white/20 cursor-not-allowed' 
                        : 'bg-[#45b7aa]/90 text-white shadow-[0_0_30px_rgba(69,183,170,0.3)] hover:bg-[#45b7aa] hover:shadow-[0_0_40px_rgba(69,183,170,0.5)] active:scale-[0.98]'
                    }
                `}
             >
                 重置并登录
             </button>
        </div>
    </div>
  )
}

export default ForgotPasswordView;