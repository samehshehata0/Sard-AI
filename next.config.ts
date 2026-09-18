import type { NextConfig } from "next";
import os from "os";

function getLocalNetworkIPs(): string[] {
  const interfaces = os.networkInterfaces();
  const ips: string[] = [];

  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name] ?? []) {
      // Only IPv4, non-internal (skips 127.0.0.1)
      if (iface.family === "IPv4" && !iface.internal) {
        ips.push(iface.address);
      }
    }
  }

  return ips;
}

const nextConfig: NextConfig = {
  // ffmpeg-static resolves a platform binary at runtime, so keep it external
  // to the server bundle.
  serverExternalPackages: ["ffmpeg-static"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "ik.imagekit.io", pathname: "/**" }],
  },
  allowedDevOrigins: getLocalNetworkIPs(),
};

export default nextConfig;
