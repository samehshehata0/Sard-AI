import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ffmpeg-static resolves a platform binary at runtime, so keep it external
  // to the server bundle.
  serverExternalPackages: ["ffmpeg-static"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "ik.imagekit.io", pathname: "/**" }],
  },
};

export default nextConfig;
