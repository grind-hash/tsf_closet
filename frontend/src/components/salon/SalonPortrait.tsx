import { useTransparentImage } from "../../hooks/useTransparentImage";

// 背景の色は四隅から読み取る(生成画像の背景は白とは限らず、薄い灰色のことも多い)
const SALON_PORTRAIT_ALPHA_OPTIONS = {
  targetColor: null,
  threshold: 12,
  featherRadius: 1.8,
};

interface SalonPortraitProps {
  src: string;
  alt: string;
  /** キャラクターの背景を透過して、サロンの背景に重ねるか */
  transparent: boolean;
  className?: string;
}

/**
 * 接客のステージに立つお客様の画像。透過の処理が終わるまでは元の画像を出し、
 * 失敗したときも元の画像のままにする(useTransparentImage が元画像へ倒す)。
 */
export default function SalonPortrait({
  src,
  alt,
  transparent,
  className,
}: SalonPortraitProps) {
  const { url } = useTransparentImage(
    src,
    transparent,
    SALON_PORTRAIT_ALPHA_OPTIONS,
  );
  return <img className={className} src={url ?? src} alt={alt} />;
}
