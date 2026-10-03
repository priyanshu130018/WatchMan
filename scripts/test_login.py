import requests

def test():
    res = requests.post('http://localhost:8000/api/auth/login', json={'email': 'aryan@gmail.com', 'password': '123456789'})
    print('Aryan Login Status:', res.status_code)
    if res.status_code == 200:
        data = res.json()
        print('User email:', data.get('user', {}).get('email'))
        print('User ID:', data.get('user', {}).get('id'))
        print('Has access_token:', bool(data.get('access_token')))
        print('Has refresh_token:', bool(data.get('refresh_token')))
    else:
        print('Response:', res.text)

    res_bharat = requests.post('http://localhost:8000/api/auth/login', json={'email': 'bharat@gmail.com', 'password': '123456789'})
    print('Bharat Login Status:', res_bharat.status_code)

if __name__ == '__main__':
    test()
