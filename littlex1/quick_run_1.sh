export base_url="localhost:8000"
export token=$(http POST $base_url/user/login username=user password=password | jq ".data.token" -r)

export node=$(http -A bearer -a $token POST "$base_url/function/create_node" | jq ".data.result.[0]" -r)

echo $node

