import {createFileRoute} from '@tanstack/react-router'; import {Auth} from '@/features/Auth'; export const Route=createFileRoute('/login')({component:()=> <Auth mode="login"/>});
