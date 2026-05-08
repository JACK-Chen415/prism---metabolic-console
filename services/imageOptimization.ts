export type OptimizedImageOptions = {
    maxSide?: number;
    quality?: number;
    mimeType?: 'image/jpeg' | 'image/webp';
};

const DEFAULT_OPTIONS: Required<OptimizedImageOptions> = {
    maxSide: 1024,
    quality: 0.72,
    mimeType: 'image/jpeg',
};

const canvasToBlob = (canvas: HTMLCanvasElement, mimeType: string, quality: number): Promise<Blob> => {
    return new Promise((resolve, reject) => {
        canvas.toBlob(
            blob => (blob ? resolve(blob) : reject(new Error('图片压缩失败'))),
            mimeType,
            quality
        );
    });
};

const getTargetSize = (width: number, height: number, maxSide: number) => {
    const longestSide = Math.max(width, height);
    if (longestSide <= maxSide) {
        return { width, height };
    }

    const scale = maxSide / longestSide;
    return {
        width: Math.round(width * scale),
        height: Math.round(height * scale),
    };
};

export const optimizeCanvasImage = async (
    sourceCanvas: HTMLCanvasElement,
    options: OptimizedImageOptions = {}
): Promise<File> => {
    const { maxSide, quality, mimeType } = { ...DEFAULT_OPTIONS, ...options };
    const target = getTargetSize(sourceCanvas.width, sourceCanvas.height, maxSide);
    const canvas = document.createElement('canvas');
    canvas.width = target.width;
    canvas.height = target.height;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
        throw new Error('无法创建图片压缩画布');
    }

    ctx.drawImage(sourceCanvas, 0, 0, target.width, target.height);
    const blob = await canvasToBlob(canvas, mimeType, quality);
    return new File([blob], `food-${Date.now()}.jpg`, { type: mimeType });
};

export const optimizeImageFile = async (
    file: File,
    options: OptimizedImageOptions = {}
): Promise<File> => {
    if (!file.type.startsWith('image/')) {
        throw new Error('请选择图片文件');
    }

    const { maxSide, quality, mimeType } = { ...DEFAULT_OPTIONS, ...options };
    const imageUrl = URL.createObjectURL(file);

    try {
        const image = new Image();
        image.decoding = 'async';
        image.src = imageUrl;
        await image.decode();

        const target = getTargetSize(image.naturalWidth, image.naturalHeight, maxSide);
        const canvas = document.createElement('canvas');
        canvas.width = target.width;
        canvas.height = target.height;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
            throw new Error('无法创建图片压缩画布');
        }

        ctx.drawImage(image, 0, 0, target.width, target.height);
        const blob = await canvasToBlob(canvas, mimeType, quality);
        return new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), { type: mimeType });
    } finally {
        URL.revokeObjectURL(imageUrl);
    }
};