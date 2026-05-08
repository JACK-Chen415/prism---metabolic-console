import React, { useRef, useState, useEffect } from 'react';
import { IntakeDraftSession, View } from '../../types';
import { IntakeAPI, TokenManager } from '../../services/api';
import { optimizeCanvasImage, optimizeImageFile } from '../../services/imageOptimization';

interface CameraViewProps {
  onViewChange: (view: View) => void;
  onPendingIntakeSessionChange: (session: IntakeDraftSession | null) => void;
}

const CameraView: React.FC<CameraViewProps> = ({ onViewChange, onPendingIntakeSessionChange }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [torchActive, setTorchActive] = useState(false);
  const [hasTorch, setHasTorch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, []);

  const startCamera = async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }

      const track = mediaStream.getVideoTracks()[0];
      const capabilities = track.getCapabilities() as any;
      if (capabilities.torch) {
        setHasTorch(true);
      }
    } catch (err: any) {
      console.error("Camera access denied or error", err);
      setError("无法访问相机，请检查权限设置");
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => {
        track.stop();
      });
      setStream(null);
    }
  };

  const toggleTorch = async () => {
    if (stream) {
      const track = stream.getVideoTracks()[0];
      try {
        await track.applyConstraints({
          advanced: [{ torch: !torchActive }]
        } as any);
        setTorchActive(!torchActive);
      } catch (e) {
        console.error("Error toggling torch", e);
      }
    }
  };

  const handleCapture = async () => {
    if (!videoRef.current || !stream || isProcessing) return;
    setIsProcessing(true);

    try {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const ctx = canvas.getContext('2d');

      if (ctx) {
        ctx.drawImage(videoRef.current, 0, 0);

        if (TokenManager.isAuthenticated()) {
          try {
            const optimizedFile = await optimizeCanvasImage(canvas);
            const session = await IntakeAPI.recognizeAndParsePhotoUpload(optimizedFile);
            onPendingIntakeSessionChange(session);
            stopCamera();
            onViewChange(View.CHAT);
          } catch (err) {
            console.error('食物识别失败:', err);
            setError('食物识别或结构化失败，请稍后重试');
          }
        }
      }
    } catch (err) {
      console.error('拍照失败:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleGalleryClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      setIsProcessing(true);

      if (TokenManager.isAuthenticated()) {
        try {
          const optimizedFile = await optimizeImageFile(file);
          const session = await IntakeAPI.recognizeAndParsePhotoUpload(optimizedFile);
          onPendingIntakeSessionChange(session);
          stopCamera();
          onViewChange(View.CHAT);
        } catch (err) {
          console.error('食物识别失败:', err);
          setError('食物识别或结构化失败，请稍后重试');
        }
      }

      setIsProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black flex flex-col items-center justify-between">
      <input
        type="file"
        accept="image/*"
        className="hidden"
        ref={fileInputRef}
        onChange={handleFileChange}
      />

      <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
        {error ? (
          <div className="text-white/60 text-center px-6">
            <span className="material-symbols-outlined text-4xl mb-2">videocam_off</span>
            <p>{error}</p>
            <button
              onClick={() => onViewChange(View.HOME)}
              className="mt-4 px-4 py-2 bg-white/10 rounded-full text-sm"
            >
              返回首页
            </button>
          </div>
        ) : (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}

        <div className="absolute top-0 left-0 right-0 p-4 flex items-center justify-between bg-gradient-to-b from-black/60 to-transparent pt-6">
          <button
            onClick={() => { stopCamera(); onViewChange(View.HOME); }}
            className="w-10 h-10 flex items-center justify-center rounded-full bg-black/20 text-white backdrop-blur-md"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
          <h2 className="text-white font-serif tracking-widest text-sm shadow-sm">食物扫描</h2>
          <div className="w-10"></div>
        </div>

        {!error && (
          <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
            <div className="w-64 h-64 border border-white/30 rounded-3xl relative">
              <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-primary rounded-tl-xl"></div>
              <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-primary rounded-tr-xl"></div>
              <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-primary rounded-bl-xl"></div>
              <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-primary rounded-br-xl"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-white/60 text-xs tracking-wider animate-pulse">寻找食物主体...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-black/90 to-transparent flex items-center justify-around px-8 pb-8">
        <button
          onClick={toggleTorch}
          disabled={!hasTorch}
          className={`w-12 h-12 rounded-full flex items-center justify-center backdrop-blur-md transition-colors ${torchActive ? 'bg-primary/20 text-primary' : 'bg-white/10 text-white hover:bg-white/20'} ${!hasTorch && 'opacity-30 cursor-not-allowed'}`}
        >
          <span className="material-symbols-outlined">{torchActive ? 'flash_on' : 'flash_off'}</span>
        </button>

        <button
          onClick={handleCapture}
          disabled={isProcessing}
          className="w-20 h-20 rounded-full border-4 border-white flex items-center justify-center bg-white/10 active:scale-95 transition-transform disabled:opacity-60"
        >
          <div className="w-16 h-16 rounded-full bg-white shadow-[0_0_15px_rgba(255,255,255,0.5)]"></div>
        </button>

        <button
          onClick={handleGalleryClick}
          disabled={isProcessing}
          className="w-12 h-12 rounded-full flex items-center justify-center bg-white/10 text-white backdrop-blur-md hover:bg-white/20 transition-colors disabled:opacity-60"
        >
          <span className="material-symbols-outlined">photo_library</span>
        </button>
      </div>
    </div>
  );
};

export default CameraView;