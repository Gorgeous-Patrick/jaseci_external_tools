export base_url="localhost:8000"
export token=$(http POST $base_url/user/login username=user password=password | jq ".data.token" -r)
http -A bearer -a $token POST "$base_url/walker/LoadFeed/$NODE"
