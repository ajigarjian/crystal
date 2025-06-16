import dynamic from 'next/dynamic'

const InteractiveMap = dynamic(
  () => import('./InteractiveMap').then(mod => ({ default: mod.InteractiveMap })),
  { 
    ssr: false,
    loading: () => <div>Loading map...</div>
  }
)

export { InteractiveMap } 