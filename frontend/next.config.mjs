/** @type {import('next').NextConfig} */
const nextConfig = {
  // 说明：
  // - 后端同源代理统一走 `src/app/api/backend/[...path]/route.ts`
  // - 避免 rewrites 与 Route Handler 双重机制导致排查困难
};

export default nextConfig;

