import React from 'react';

interface SplashScreenProps {
  isExiting: boolean;
}

const SplashScreen: React.FC<SplashScreenProps> = ({ isExiting }) => {
  return (
    <div className={`fixed inset-0 z-50 flex flex-col items-center justify-between bg-[#050809] transition-opacity duration-700 ${isExiting ? 'opacity-0' : 'opacity-100'}`}>
      
      {/* Abstract Background */}
      <div 
        className="absolute inset-0 z-0 opacity-20 bg-cover bg-center mix-blend-overlay"
        style={{ backgroundImage: 'url("/images/bg-texture.png")' }}
      />
      
      <div className="relative z-10 flex flex-grow w-full items-center justify-center p-8">
        {/* Glow Effect */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-primary/5 rounded-full blur-[80px]"></div>
        
        {/* Prism Animation */}
        <div className="relative w-full max-w-[320px] aspect-square flex flex-col items-center justify-center">
          <div 
            className="w-full h-full bg-contain bg-center bg-no-repeat drop-shadow-[0_0_30px_rgba(17,196,212,0.3)] animate-pulse"
            style={{
              backgroundImage: 'url("/images/prism-logo.png")',
              animationDuration: '4s'
            }}
          />
        </div>
      </div>

      <div className="relative z-10 w-full px-6 pb-20 pt-4 flex flex-col items-center text-center">
        <div className="mb-8 flex flex-col items-center gap-3">
          <h1 className="text-white text-5xl font-light tracking-[0.2em] leading-tight ml-3 font-display">
            PRISM
          </h1>
          <span className="text-white/90 text-2xl font-light tracking-[0.1em] mt-1 font-serif">
            (食鉴)
          </span>
        </div>
        
        <div className="h-[1px] w-12 bg-gradient-to-r from-transparent via-primary to-transparent mb-8 opacity-40"></div>
        
        <div className="flex flex-col items-center gap-2">
          <h2 className="text-white/80 text-xl font-normal tracking-[0.3em] font-serif">
            透视美食本质
          </h2>
          <p className="text-primary/70 text-[10px] font-medium uppercase tracking-[0.2em] opacity-60 font-display mt-1">
            See the Essence of Food
          </p>
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;