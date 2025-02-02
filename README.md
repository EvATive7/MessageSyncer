<div align="center">

<img src="./doc/logo.png" width="150" height="">

# MessageSyncer

An fully asynchronous push framework.

</div>

## Feature

- Fully asynchronous
- Low performance-overhead
- Hot-reload
- Easy to develop

## Get Started

### From Source

1. `git clone`
1. Setup python. 3.11.9 is tested
1. Run `setup.ps1` or `setup.sh`
1. Start process by `run.ps1` or `run.sh`

<!--### Binary

1. Run `MessageSyncer` or `MessageSyncer.exe`
-->

### Docker

1. Download [Compose File](../docker/compose.yml)
1. Run `docker compose -f compose.yml up -d`

### Terminology

- **Adapter**: A module that interacts with external message interfaces.
- **Adapter class**: A class created by adapter developers, usually named after the interface name, such as `Weibo` or `Onebot11`.
- **Adapter instance**: An instance of the Adapter class, distinguished by an ID. If there is no ID, it is considered a singleton of the class name, and should be ensured to work in singleton mode.
- **Getter**: An Adapter that acts as a message source, periodically refreshes and obtains message lists and details. The name of a Getter instance is `{getter_class_name}.{id}`, or `{getter_class_name}` (singleton mode).
- **Pusher**: An Adapter that sends messages. The name of a Pusher instance is `{pusher_class_name}.{id}`, or `{pusher_class_name}` (singleton mode).
- **Pair**: consists of `{getter_instance} {pusher_instance}.{push_to_where}`, for example `Weibo.1234567890 Onebot.bot1.user1`.

## Develop

[Developing Guide](./doc/dev.md)

## License

This project is licensed under the GPL3.0 - see the [LICENSE](LICENSE) file for details.

The project references the following open source code via copy:

- [dc-schema](https://github.com/Peter554/dc_schema) (Original project follows MIT License)
