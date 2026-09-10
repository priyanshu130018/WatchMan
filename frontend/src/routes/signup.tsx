import {createFileRoute} from '@tanstack/react-router'; import {Auth} from '@/features/Auth'; export const Route=createFileRoute('/signup')({component:()=> <Auth mode="signup"/>});
