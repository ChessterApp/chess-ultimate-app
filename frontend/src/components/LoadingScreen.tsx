'use client'

import React from 'react';
import { useTranslations } from 'next-intl';

interface LoadingScreenProps {
  isVisible: boolean;
}

const LoadingScreen: React.FC<LoadingScreenProps> = ({ isVisible }) => {
  const t = useTranslations('common');
  if (!isVisible) return null;

  return (
    <>
      <style jsx global>{`
        @keyframes chessWave {
          0% {
            transform: translate3D(0,0,0) scale(1) rotateY(0deg);
            color: #ff0080;
            text-shadow: 0 0 15px rgba(255, 0, 128, 0.5), 0 0 30px rgba(255, 0, 128, 0.3);
          }
          12% {
            transform: translate3D(6px,-12px,8px) scale(1.4) rotateY(20deg);
            color: #ff4080;
            text-shadow: 0 0 25px rgba(255, 64, 128, 0.9), 0 0 50px rgba(255, 64, 128, 0.6);
          }
          15% {
            color: #ff8040;
            text-shadow: 0 0 30px rgba(255, 128, 64, 1), 0 0 60px rgba(255, 128, 64, 0.7);
          }
          24% {
            transform: translate3D(0,0,0) scale(1) rotateY(0deg);
            color: #ffff00;
            text-shadow: 0 0 25px rgba(255, 255, 0, 0.8), 0 0 50px rgba(255, 255, 0, 0.5);
          }
          36% {
            color: #80ff40;
            text-shadow: 0 0 20px rgba(128, 255, 64, 0.7), 0 0 40px rgba(128, 255, 64, 0.4);
          }
          48% {
            color: #40ff80;
            text-shadow: 0 0 18px rgba(64, 255, 128, 0.6), 0 0 35px rgba(64, 255, 128, 0.3);
          }
          60% {
            color: #00ffff;
            text-shadow: 0 0 15px rgba(0, 255, 255, 0.5), 0 0 30px rgba(0, 255, 255, 0.3);
          }
          72% {
            color: #4080ff;
            text-shadow: 0 0 15px rgba(64, 128, 255, 0.5), 0 0 30px rgba(64, 128, 255, 0.3);
          }
          84% {
            color: #8040ff;
            text-shadow: 0 0 20px rgba(128, 64, 255, 0.7), 0 0 40px rgba(128, 64, 255, 0.4);
          }
          96% {
            color: #ff00ff;
            text-shadow: 0 0 25px rgba(255, 0, 255, 0.8), 0 0 50px rgba(255, 0, 255, 0.5);
          }
          100% {
            transform: translate3D(0,0,0) scale(1) rotateY(0deg);
            color: #ff0080;
            text-shadow: 0 0 15px rgba(255, 0, 128, 0.5), 0 0 30px rgba(255, 0, 128, 0.3);
          }
        }

        @keyframes pulse {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .loading-screen-overlay {
          position: fixed !important;
          top: 0 !important;
          left: 0 !important;
          width: 100% !important;
          height: 100% !important;
          background-color: var(--surface-page, #FAFAFA) !important;
          display: flex !important;
          justify-content: center !important;
          align-items: center !important;
          z-index: 9999 !important;
          /* no fade-in — overlay must appear instantly to prevent piece flash */
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
        }

        .loading-screen-overlay::before {
          content: '' !important;
          position: fixed !important;
          top: 0 !important;
          left: 0 !important;
          width: 100% !important;
          height: 100% !important;
          background-image:
            linear-gradient(45deg, rgba(0,0,0,0.03) 25%, transparent 25%),
            linear-gradient(-45deg, rgba(0,0,0,0.03) 25%, transparent 25%),
            linear-gradient(45deg, transparent 75%, rgba(0,0,0,0.03) 75%),
            linear-gradient(-45deg, transparent 75%, rgba(0,0,0,0.03) 75%) !important;
          background-size: 60px 60px !important;
          background-position: 0 0, 0 30px, 30px -30px, -30px 0px !important;
          z-index: -1 !important;
          opacity: 0.1 !important;
        }

        #loadingWave {
          display: flex !important;
          gap: 20px !important;
          perspective: 100px !important;
          transform-style: preserve-3d !important;
          position: relative !important;
        }

        .chess-piece {
          width: 48px !important;
          height: 48px !important;
          position: relative !important;
          display: flex !important;
          justify-content: center !important;
          align-items: center !important;
          font-size: 36px !important;
          animation: chessWave 2.4s ease infinite !important;
          transform-origin: 50% 50% !important;
          transform-style: preserve-3d !important;
          cursor: pointer !important;
          transition: transform 0.1s ease !important;
        }

        .chess-piece:hover {
          transform: scale(1.1) !important;
        }

        .chess-piece:nth-child(1) { animation-delay: 0s !important; }
        .chess-piece:nth-child(2) { animation-delay: 0.1s !important; }
        .chess-piece:nth-child(3) { animation-delay: 0.2s !important; }
        .chess-piece:nth-child(4) { animation-delay: 0.3s !important; }
        .chess-piece:nth-child(5) { animation-delay: 0.4s !important; }
        .chess-piece:nth-child(6) { animation-delay: 0.5s !important; }

        .loading-text {
          position: absolute !important;
          bottom: -50px !important;
          left: 50% !important;
          transform: translateX(-50%) !important;
          color: var(--text-secondary, rgba(0,0,0,0.5)) !important;
          font-size: 16px !important;
          letter-spacing: 2px !important;
          text-transform: uppercase !important;
          animation: pulse 2s ease-in-out infinite !important;
        }

        @media (max-width: 768px) {
          .chess-piece {
            width: 36px !important;
            height: 36px !important;
            font-size: 28px !important;
          }
          .chess-piece.king { font-size: 32px !important; }
          .chess-piece.queen { font-size: 30px !important; }
          .chess-piece.rook, .chess-piece.bishop, .chess-piece.knight { font-size: 28px !important; }
          .chess-piece.pawn { font-size: 24px !important; }
          #loadingWave {
            gap: 15px !important;
          }
        }

        @media (max-width: 380px) {
          .chess-piece {
            font-size: 22px !important;
          }
          #loadingWave {
            gap: 10px !important;
          }
        }
      `}</style>
      <div className="loading-screen-overlay" style={{position:'fixed',top:0,left:0,width:'100%',height:'100%',display:'flex',justifyContent:'center',alignItems:'center',zIndex:9999}}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div id="loadingWave">
          <div className="chess-piece king">♚</div>
          <div className="chess-piece queen">♛</div>
          <div className="chess-piece rook">♜</div>
          <div className="chess-piece bishop">♝</div>
          <div className="chess-piece knight">♞</div>
          <div className="chess-piece pawn">♟</div>
          <div className="loading-text">{t('loading')}</div>
        </div>
        </div>
      </div>
    </>
  );
};

export default LoadingScreen;
