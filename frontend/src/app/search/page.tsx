"use client";

import Link from 'next/link';
import Image from 'next/image';

export default function SearchPage() {
  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      {/* Header with logo */}
      <div className="flex h-16 shrink-0 items-center justify-between px-4">
        <div className="flex items-center">
          <Link href="/">
            <div className="flex items-center cursor-pointer hover:opacity-80 transition-opacity">
              <img 
                src="/images/crystal-icon.png" 
                alt="Crystal Logo" 
                className="h-6 w-6 filter brightness-0" 
              />
              <h1 className="text-lg font-bold dark:text-white" style={{ fontFamily: 'Satoshi, sans-serif' }}>Crystal</h1>
            </div>
          </Link>
        </div>
      </div>
      
      {/* Page content will go here */}
    </div>
  );
}
