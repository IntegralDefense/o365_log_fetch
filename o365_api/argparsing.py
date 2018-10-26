def add_arg_parser_args(argument_parser):
    argument_parser.add_argument(
        "-s",
        "--start_time",
        help="Integer representing the desired start time in epoch format",
    )
    argument_parser.add_argument(
        "-e",
        "--end_time",
        help="Integer representing the desired stop time in epoch format",
    )
    """
    argument_parser.add_argument(
        "-l",
        "--log_level",
        help="Set logging level",
    )
    """
